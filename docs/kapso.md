# WhatsApp con Kapso

El webhook es la ruta `POST /whatsapp` del backend (`apps/api/app/routes/whatsapp.py`). Desde afuera queda en `https://usaprais.com/api/whatsapp` (la web reenvía `/api/*`), o en la URL propia del servicio `prais-api` de Cloud Run: `<url de prais-api>/whatsapp`.

## Qué hace

1. Verifica la firma: un HMAC-SHA256 en hex del cuerpo crudo, con `KAPSO_WEBHOOK_SECRET`, que llega en el header `X-Webhook-Signature`. Si no coincide, responde 401.
2. Ignora todo evento que no sea `whatsapp.message.received` (header `X-Webhook-Event`).
3. Encola **una tarea por mensaje de texto** en Cloud Tasks y responde 200 de inmediato, porque Kapso exige respuesta en menos de 10 segundos. El nombre de la tarea es el `sha256` del `message.id`: si Kapso reintenta la entrega, Cloud Tasks la rechaza como duplicada y la persona no recibe dos respuestas. Si no se puede encolar, responde 500 y Kapso reintenta.
4. La cola llama a `POST /internal/whatsapp-task` de esta misma API, que le pasa el texto al agente y contesta por la API REST de Kapso con `httpx`: `POST https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages`, con el header `X-API-Key`. Kapso no tiene SDK para Python. Si hay al menos dos ofertas con precio y link, manda un carrusel (`type: carousel`). El texto de arriba es el veredicto (máximo 250 caracteres). Cada tarjeta abre la compra y, en 160 caracteres, muestra precio y vendedor en negrita, canal, confianza, envío, reseñas y tasa. La foto es la del anuncio; si no hay, una foto pública del producto servida en `/card-images/` con «imagen de Prais» encima. Esa URL tiene que ser pública (`PUBLIC_BASE_URL`, o `SELF_URL` en Cloud Run). Si no se puede armar el carrusel, manda el veredicto como texto.
5. Si la tarea falla, la cola la reintenta hasta 5 veces (`TASKS_MAX_ATTEMPTS`, cola `prais-jobs`, espera de 10 a 300 s entre intentos). En el último intento fallido le avisa a la persona con el mensaje de disculpa, en vez de dejarla sin respuesta.

`/internal/whatsapp-task` es **interna**, no es un contrato público: la llama Cloud Tasks con un token OIDC de la cuenta `prais-api-run`. La ruta valida el token (audiencia `SELF_URL`, email igual a `TASKS_OIDC_SA`) y responde 401 si no. Como el servicio es público, ese token es lo único que la protege.

Acepta mensajes sueltos y también lotes, si se activa el buffering en Kapso: cada mensaje de texto del lote es su propia tarea. Por ahora solo procesa mensajes de texto.

**Sin cola, en local.** Si `TASKS_QUEUE` no está definida (lo normal con `pnpm dev`), el webhook no encola: responde 200 y procesa en segundo plano con `BackgroundTasks`, sin reintentos ni deduplicación.

## Configurar en Kapso

1. Crea un webhook de WhatsApp para el número, apuntando a `https://usaprais.com/api/whatsapp`, con el evento `whatsapp.message.received` y la versión 2 del payload.
2. Copia el secreto del webhook a `KAPSO_WEBHOOK_SECRET` y la API key del proyecto a `KAPSO_API_KEY`. En local van en `apps/api/.env`; en producción, en el secreto `prais-api-secrets` (`infra/40-secrets.sh`).
3. Opcional: activa el buffering (5 segundos), para que los mensajes seguidos de una persona lleguen juntos.

La cola, sus variables y los permisos están en [gcp.md](gcp.md).

## Pendiente

- Si un mensaje no trae `from` (los payloads nuevos pueden traer solo `business_scoped_user_id`), hoy se ignora.
- Un reintento de la tarea vuelve a correr el agente, así que si falló al enviar y no al pensar, la conversación guarda ese turno dos veces.

## Docs

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Eventos de mensajes](https://docs.kapso.ai/docs/platform/webhooks/message-events.md)
- [Enviar texto](https://docs.kapso.ai/docs/whatsapp/send-messages/text.md)
