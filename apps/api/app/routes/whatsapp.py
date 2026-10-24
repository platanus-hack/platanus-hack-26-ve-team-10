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
from app.lib.tasks import enqueue_whatsapp_event, queue_enabled

router = APIRouter()
log = logging.getLogger("prais.whatsapp")

# API de mensajes de Kapso (compatible con la de Meta): https://docs.kapso.ai/docs/whatsapp/send-messages/text.md
KAPSO_MESSAGES_URL = "https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages"

# Debe coincidir con --max-attempts de la cola (infra/35-tasks.sh). En el último intento fallido
# se le avisa a la persona en vez de dejarla sin respuesta.
MAX_ATTEMPTS = int(os.environ.get("TASKS_MAX_ATTEMPTS", "5"))


def _valid_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("KAPSO_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _text_message(event: dict[str, Any]) -> tuple[str, str, str] | None:
    """(phone_number_id, remitente, texto) si el evento es un mensaje de texto procesable."""
    message = event.get("message") or {}
    phone_number_id = event.get("phone_number_id")
    text = ((message.get("text") or {}).get("body") or "").strip()
    sender = message.get("from")
    if message.get("type") != "text" or not text or not sender or not phone_number_id:
        return None
    return phone_number_id, sender, text


async def _send_text(phone_number_id: str, to: str, body: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            KAPSO_MESSAGES_URL.format(phone_number_id=phone_number_id),
            headers={"X-API-Key": os.environ["KAPSO_API_KEY"]},
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}},
        )
        response.raise_for_status()


async def _reply(event: dict[str, Any]) -> None:
    parsed = _text_message(event)
    if not parsed:
        return
    phone_number_id, sender, text = parsed
    answer = await ask_prais(f"whatsapp:{sender}", text)
    await _send_text(phone_number_id, sender, answer)


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
    events = [e for e in (payload["data"] if payload.get("batch") else [payload]) if _text_message(e)]

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
        await _reply(event)
    except Exception:
        log.exception("whatsapp task failed (intento %s de %s)", attempt, MAX_ATTEMPTS)
        if attempt < MAX_ATTEMPTS:
            return Response(status_code=500)
        parsed = _text_message(event)
        if parsed:
            try:
                await _send_text(parsed[0], parsed[1], FALLBACK_REPLY)
            except Exception:
                log.exception("whatsapp fallback failed")
    return Response(status_code=200)
