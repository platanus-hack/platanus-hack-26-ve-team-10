import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import PlainTextResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.agent import FALLBACK_REPLY, PraisAnswer, ask_prais
from app.agents.listing import button_message, clamp_summary, shopping_message
from app.lib import replies
from app.lib.replies import ReplyInProgress
from app.lib.tasks import enqueue_whatsapp_event, queue_enabled

router = APIRouter()
log = logging.getLogger("prais.whatsapp")

# API de mensajes de Kapso (compatible con la de Meta): https://docs.kapso.ai/docs/whatsapp/send-messages/text.md
KAPSO_MESSAGES_URL = "https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages"

# Debe coincidir con --max-attempts de la cola (infra/35-tasks.sh). En el último intento fallido
# se le avisa a la persona en vez de dejarla sin respuesta.
MAX_ATTEMPTS = int(os.environ.get("TASKS_MAX_ATTEMPTS", "5"))

# Una persona, un turno. Los mensajes que llegan mientras se arma la respuesta
# se suman y sale una sola contestación, no una búsqueda por mensaje.
# QUIET_S espera un silencio corto para que dos burbujas seguidas sean ese turno.
# Las pruebas lo ponen en 0. Kapso puede bufferar 5 s; esto cubre el caso local.
QUIET_S = 1.5
QUIET_CAP_S = 4.0

# Cloud Run corta la request a los 300 s. Sin tope propio, un turno que se cuelga se lleva
# ese plazo entero: la cola ya dio la tarea por hecha y la persona se queda con el indicador
# de "escribiendo" encendido, sin respuesta y sin reintento. Cortar antes y avisar vale más
# que el silencio. El plazo de replies.LEASE_SECONDS tiene que quedar por encima de esto.
TURN_TIMEOUT_S = float(os.environ.get("TURN_TIMEOUT_S", "120"))
TIMEOUT_REPLY = "La búsqueda está tardando más de lo normal. Dime el producto otra vez, por favor."
_inbox: dict[str, list[tuple[str, str | None, str]]] = {}
_running: set[str] = set()


def _valid_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("KAPSO_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _reply_title(interactive: dict[str, Any]) -> str:
    """Título de la fila o del botón. Kapso documenta button_reply así; la lista usa list_reply."""
    kind = interactive.get("type")
    if kind == "list_reply":
        reply = interactive.get("list_reply") or {}
    elif kind == "button_reply":
        reply = interactive.get("button_reply") or {}
    else:
        return ""
    if not isinstance(reply, dict):
        return ""
    return str(reply.get("title") or reply.get("id") or "").strip()


def _inbound_text(event: dict[str, Any]) -> tuple[str, str, str] | None:
    """(phone_number_id, remitente, texto) de un texto o de una fila tocada."""
    message = event.get("message") or {}
    phone_number_id = event.get("phone_number_id")
    sender = message.get("from")
    if not sender or not phone_number_id:
        return None
    kind = message.get("type")
    if kind == "text":
        text = ((message.get("text") or {}).get("body") or "").strip()
    elif kind == "interactive":
        interactive = message.get("interactive") or {}
        text = _reply_title(interactive if isinstance(interactive, dict) else {})
    else:
        return None
    if not text:
        return None
    return phone_number_id, sender, text


async def _post_message(phone_number_id: str, payload: dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            KAPSO_MESSAGES_URL.format(phone_number_id=phone_number_id),
            headers={"X-API-Key": os.environ["KAPSO_API_KEY"]},
            json=payload,
        )
        if response.is_error:
            # Kapso dice en el cuerpo qué campo rechazó. Sin esto un 400 es solo silencio.
            log.error("kapso respondió %s: %s", response.status_code, response.text[:500])
        response.raise_for_status()


def _text_payload(to: str, body: str) -> dict[str, Any]:
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}


async def _send_text(phone_number_id: str, to: str, body: str) -> None:
    await _post_message(phone_number_id, _text_payload(to, body))


# WhatsApp apaga el indicador al enviar un mensaje o a los ~25 s, y una búsqueda
# puede tardar más. Mandarlo una sola vez deja a la persona viendo el indicador
# apagarse, que es peor que no ponerlo: mientras el agente trabaja, se reemite.
TYPING_EVERY_S = 20


async def _keep_typing(phone_number_id: str, message_id: str) -> None:
    while True:
        await asyncio.sleep(TYPING_EVERY_S)
        await _show_typing(phone_number_id, message_id)


def _keep_typing_alive(phone_number_id: str, message_id: str | None) -> asyncio.Task | None:
    """El primero ya salió con _show_typing: esto solo lo mantiene vivo."""
    if not message_id or not os.environ.get("KAPSO_API_KEY"):
        return None
    return asyncio.create_task(_keep_typing(phone_number_id, message_id))


async def _stop_typing(typing: asyncio.Task | None) -> None:
    if typing is None:
        return
    typing.cancel()
    try:
        await typing
    except asyncio.CancelledError:
        pass
    except Exception:
        log.warning("whatsapp typing stop failed", exc_info=True)


def _message_id(event: dict[str, Any]) -> str | None:
    message_id = (event.get("message") or {}).get("id")
    if isinstance(message_id, str) and message_id:
        return message_id
    return None


async def _send_saved(phone_number_id: str, message_id: str | None, payload: dict[str, Any]) -> None:
    await _post_message(phone_number_id, payload)
    if message_id:
        await replies.complete(message_id, payload)


def _result_body(answer: PraisAnswer) -> str:
    """El veredicto, debajo del producto con el que se buscó de verdad.

    Lo que la conversación fue fijando no se veía en ningún lado: si quedó mal, la
    persona se enteraba al leer tarjetas de otra cosa. Ahora lo lee antes.
    """
    summary = clamp_summary(answer.text)
    product = " ".join(answer.product.split())
    if not product or _folded(product) in _folded(summary):
        return summary
    return f"*{product}*\n{summary}"


def _folded(text: str) -> str:
    return " ".join(text.lower().split())


async def _outbound(sender: str, answer: PraisAnswer) -> dict[str, Any]:
    body = _result_body(answer)
    try:
        shopping = await shopping_message(sender, answer.listings, body)
    except Exception:
        log.exception("whatsapp cards failed")
        shopping = None
    if shopping is not None:
        return shopping
    return _text_payload(sender, body)


_REFINE_BODY = "¿Lo afinamos?"
_DEAD_END_BODY = "Puedo buscar más amplio:"


async def _send_followups(phone_number_id: str, to: str, answer: PraisAnswer) -> None:
    """Afinar si hubo precios, salir si no hubo. En su propio mensaje: WhatsApp no
    deja colgar botones de un carrusel. No se guardan para el reintento de la cola:
    lo que no puede perderse son las ofertas, y esas sí se guardan."""
    if not answer.buttons:
        return
    body = _REFINE_BODY if answer.priced else _DEAD_END_BODY
    payload = button_message(to, body, answer.buttons)
    if payload is None:
        return
    try:
        await _post_message(phone_number_id, payload)
    except Exception:
        log.exception("whatsapp followups failed")


async def _show_typing(phone_number_id: str, message_id: str | None) -> None:
    """Marca leído y muestra que Prais escribe. Lo hace el webhook, no el modelo.

    Kapso documenta el indicador en el mismo POST de mensajes, junto con status read.
    Una tool de envío en el agente se saltaría las tarjetas.
    """
    if not message_id or not os.environ.get("KAPSO_API_KEY"):
        return
    try:
        await _post_message(
            phone_number_id,
            {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {"type": "text"},
            },
        )
    except Exception:
        log.exception("whatsapp typing failed")


def _ack_text(product: str) -> str:
    """Qué se entendió, antes de los 45 s de búsqueda y no después.

    Promete lo que Prais hace, no lo que va a encontrar: decir "te traigo lo más
    confiable" antes de buscar es prometer un resultado que puede no existir.
    La segunda frase es la que vale: deja corregir mientras todavía sirve, y la
    corrección ya la recoge el bucle, que descarta la respuesta y rehace la búsqueda.
    """
    if "http://" in product or "https://" in product:
        return "Dale! Veo qué venden en esa página y comparo el precio."
    return f"Dale! Busco *{product}* y te digo dónde está más barato. Si no es ese, dime cuál."


def _acknowledge(phone_number_id: str, to: str):
    """El closure que el agente llama cuando ya decidió qué va a buscar."""

    async def send(product: str) -> None:
        await _post_message(phone_number_id, _text_payload(to, _ack_text(product)))

    return send


async def _drain(sender: str) -> None:
    """Responde cuando ya no queda texto nuevo de esta persona."""
    pending_ids: list[str | None] = []
    phone_number_id = ""
    said: list[str] = []
    waited = 0.0
    while True:
        if QUIET_S > 0 and waited < QUIET_CAP_S:
            await asyncio.sleep(QUIET_S)
            waited += QUIET_S
        batch = _inbox.pop(sender, [])
        if not batch and not said:
            return
        if batch:
            phone_number_id = batch[-1][0]
            pending_ids.extend(item[1] for item in batch)
            said.extend(item[2] for item in batch)
        if _inbox.get(sender) and waited < QUIET_CAP_S:
            continue
        text = "\n".join(said)
        last_id = next((item for item in reversed(pending_ids) if item), None)
        await _show_typing(phone_number_id, last_id)
        typing = _keep_typing_alive(phone_number_id, last_id)
        try:
            answer = await asyncio.wait_for(
                ask_prais(f"whatsapp:{sender}", text, _acknowledge(phone_number_id, sender)),
                TURN_TIMEOUT_S,
            )
        except TimeoutError:
            log.warning("whatsapp turn timed out after %ss", TURN_TIMEOUT_S)
            answer = PraisAnswer(text=TIMEOUT_REPLY)
        finally:
            await _stop_typing(typing)
        if _inbox.get(sender):
            continue
        payload = await _outbound(sender, answer)
        if _inbox.get(sender):
            continue
        try:
            await _post_message(phone_number_id, payload)
        except Exception:
            log.exception("whatsapp send failed")
            if payload.get("type") == "text":
                return
            # El carrusel se fue sin salir (un título largo, un campo de más). El veredicto
            # en texto plano vale más que dejar a la persona sin nada.
            payload = _text_payload(sender, _result_body(answer))
            try:
                await _post_message(phone_number_id, payload)
            except Exception:
                log.exception("whatsapp text fallback failed")
                return
        for message_id in pending_ids:
            if message_id:
                await replies.complete(message_id, payload)
        pending_ids = []
        said = []
        await _send_followups(phone_number_id, sender, answer)
        if not _inbox.get(sender):
            return


async def _drain_if_idle(sender: str) -> None:
    if sender in _running:
        return
    _running.add(sender)
    try:
        await _drain(sender)
    finally:
        _running.discard(sender)
        if _inbox.get(sender):
            await _drain_if_idle(sender)


async def _reply(event: dict[str, Any], *, takeover: bool = False) -> None:
    parsed = _inbound_text(event)
    if not parsed:
        return
    phone_number_id, sender, text = parsed
    message_id = _message_id(event)
    if message_id:
        claim = await replies.claim(message_id, takeover=takeover)
        if claim.kind == "done" and claim.payload is not None:
            await _post_message(phone_number_id, claim.payload)
            return
        if claim.kind == "in_progress":
            raise ReplyInProgress()
    _inbox.setdefault(sender, []).append((phone_number_id, message_id, text))
    await _drain_if_idle(sender)


async def _reply_all(events: list[dict[str, Any]]) -> None:
    for event in events:
        try:
            await _reply(event)
        except Exception:
            log.exception("whatsapp reply failed")


# Webhook de Kapso. La firma se calcula sobre el cuerpo crudo, por eso se lee como bytes.
@router.post("/whatsapp")
async def whatsapp(request: Request, background: BackgroundTasks):
    raw_body = await request.body()
    if not _valid_signature(raw_body, request.headers.get("x-webhook-signature")):
        return PlainTextResponse("Firma inválida", status_code=401)
    if request.headers.get("x-webhook-event") != "whatsapp.message.received":
        return Response(status_code=200)

    payload = json.loads(raw_body)
    events = [e for e in (payload["data"] if payload.get("batch") else [payload]) if _inbound_text(e)]

    # Kapso exige un 200 en menos de 10 segundos. Con cola, encolar tarda milisegundos y la tarea
    # se reintenta si algo falla; si no se puede encolar, el 500 hace que Kapso reintente la entrega.
    if queue_enabled():
        try:
            for event in events:
                await enqueue_whatsapp_event(event)
        except Exception:
            log.exception("whatsapp enqueue failed")
            return Response(status_code=500)
    else:
        # Local, sin cola: el agente trabaja después de responder (en Cloud Run haría falta
        # --no-cpu-throttling).
        background.add_task(_reply_all, events)
    return Response(status_code=200)


async def _valid_task_token(authorization: str | None) -> bool:
    """El token OIDC que Cloud Tasks firma con la cuenta de servicio de esta API."""
    audience, expected_email = os.environ.get("SELF_URL"), os.environ.get("TASKS_OIDC_SA")
    if not authorization or not authorization.startswith("Bearer ") or not audience or not expected_email:
        return False
    try:
        claims = await asyncio.to_thread(
            id_token.verify_oauth2_token, authorization.removeprefix("Bearer "), google_requests.Request(), audience
        )
    except ValueError:
        return False
    return claims.get("email") == expected_email and claims.get("email_verified") is True


# Interna: la llama Cloud Tasks, no Kapso ni la web. El servicio es público, así que el token
# OIDC es lo único que la protege. 200 = tarea hecha; un error 5xx hace que la cola reintente.
@router.post("/internal/whatsapp-task")
async def whatsapp_task(request: Request):
    if not await _valid_task_token(request.headers.get("authorization")):
        return PlainTextResponse("No autorizado", status_code=401)

    event = await request.json()
    attempt = int(request.headers.get("x-cloudtasks-taskretrycount", "0")) + 1
    try:
        await _reply(event, takeover=attempt >= MAX_ATTEMPTS)
    except ReplyInProgress:
        log.info("whatsapp task still in progress (intento %s de %s)", attempt, MAX_ATTEMPTS)
        return Response(status_code=500)
    except Exception:
        log.exception("whatsapp task failed (intento %s de %s)", attempt, MAX_ATTEMPTS)
        if attempt < MAX_ATTEMPTS:
            return Response(status_code=500)
        parsed = _inbound_text(event)
        if parsed:
            try:
                await _send_text(parsed[0], parsed[1], FALLBACK_REPLY)
            except Exception:
                log.exception("whatsapp fallback failed")
    return Response(status_code=200)
