# WhatsApp con Kapso

El webhook es la ruta `POST /whatsapp` del backend (`apps/api/src/routes/whatsapp.ts`). Desde afuera queda en `https://usaprais.com/api/whatsapp`, o en la URL propia del backend si el deploy lo publica aparte.

## Qué hace

1. Verifica la firma: un HMAC-SHA256 en hex del cuerpo crudo, con `KAPSO_WEBHOOK_SECRET`, que llega en el header `X-Webhook-Signature`. Si no coincide, responde 401.
2. Ignora todo evento que no sea `whatsapp.message.received` (header `X-Webhook-Event`).
3. Responde 200 de inmediato, porque Kapso exige respuesta en menos de 10 segundos.
4. Después de responder, le pasa el texto al agente y contesta por la API de Kapso con `@kapso/whatsapp-cloud-api`.

Acepta mensajes sueltos y también lotes, si se activa el buffering en Kapso. Por ahora solo procesa mensajes de texto.

## Configurar en Kapso

1. Crea un webhook de WhatsApp para el número, apuntando a `https://usaprais.com/api/whatsapp`, con el evento `whatsapp.message.received` y la versión 2 del payload.
2. Copia el secreto del webhook a `KAPSO_WEBHOOK_SECRET` y la API key del proyecto a `KAPSO_API_KEY`.
3. Opcional: activa el buffering (5 segundos), para que los mensajes seguidos de una persona lleguen juntos.

En Cloud Run hace falta `--no-cpu-throttling`, o el trabajo que sigue después del 200 se queda sin CPU (ver [gcp.md](gcp.md)).

## Pendiente

- Si un mensaje no trae `from` (los payloads nuevos pueden traer solo `business_scoped_user_id`), hoy se ignora.
- Kapso puede reintentar un envío. Si pasa en la demo, deduplica por `message.id`.

## Docs

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Eventos de mensajes](https://docs.kapso.ai/docs/platform/webhooks/message-events.md)
- [SDK de TypeScript](https://docs.kapso.ai/docs/whatsapp/typescript-sdk/introduction.md)
