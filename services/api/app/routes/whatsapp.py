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

from app.agent import FALLBACK_REPLY, ask_prais
from app.agents.listing import clamp_summary, shopping_message
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
        response.raise_for_status()


def _text_payload(to: str, body: str) -> dict[str, Any]:
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}


async def _send_text(phone_number_id: str, to: str, body: str) -> None:
    await _post_message(phone_number_id, _text_payload(to, body))


def _message_id(event: dict[str, Any]) -> str | None:
    message_id = (event.get("message") or {}).get("id")
    if isinstance(message_id, str) and message_id:
        return message_id
    return None


async def _send_saved(phone_number_id: str, message_id: str | None, payload: dict[str, Any]) -> None:
    await _post_message(phone_number_id, payload)
    if message_id:
        await replies.complete(message_id, payload)


async def _outbound(sender: str, answer: Any) -> dict[str, Any]:
    try:
        shopping = await shopping_message(sender, answer.listings, answer.text)
    except Exception:
        log.exception("whatsapp cards failed")
        shopping = None
    if shopping is not None:
        return shopping
    return _text_payload(sender, clamp_summary(answer.text))


async def _drain(sender: str) -> None:
    """Responde cuando ya no queda texto nuevo de esta persona."""
    pending_ids: list[str | None] = []
    phone_number_id = ""
    while True:
        batch = _inbox.pop(sender, [])
        if not batch:
            return
        phone_number_id = batch[-1][0]
        pending_ids.extend(item[1] for item in batch)
        text = "\n".join(item[2] for item in batch)
        answer = await ask_prais(f"whatsapp:{sender}", text)
        if _inbox.get(sender):
            continue
        payload = await _outbound(sender, answer)
        if _inbox.get(sender):
            continue
        try:
            await _post_message(phone_number_id, payload)
        except Exception:
            log.exception("whatsapp send failed")
            return
        for message_id in pending_ids:
            if message_id:
                await replies.complete(message_id, payload)
        pending_ids = []
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
