# WhatsApp con Kapso: apps/whatsapp

La gente le escribe a Prais por WhatsApp y recibe el mejor precio. [Kapso](https://docs.kapso.ai) nos da el número, nos avisa por webhook cuando llega un mensaje y nos deja responder por su API.

## Flujo

```
Mensaje ─► Kapso ─► POST wa.usaprais.com/webhook (Cloud Run)
                      1. Verifica la firma
                      2. Encola una tarea en Cloud Tasks
                      3. Responde 200
Cloud Tasks ─► POST /process ─► agente /search ─► respuesta ─► Kapso ─► WhatsApp
```

## Recibir

- Kapso exige un 200 en menos de 10 segundos. No proceses dentro del webhook: encola en Cloud Tasks y responde. En Cloud Run, la CPU se reduce después de responder, así que tampoco sirve dejar trabajo corriendo en segundo plano.
- Verifica la firma: es un HMAC-SHA256 del cuerpo, con el secreto del webhook, que llega en el header `x-kapso-signature`. Si no coincide, responde 401 y no proceses nada.
- El evento llega en el header `X-Webhook-Event`. Por ahora solo nos importa `whatsapp.message.received`.
- Usa la versión 2 del payload (header `X-Webhook-Payload-Version`).
- Activa el buffering: junta los mensajes seguidos de una persona (5 segundos por defecto) y trátalos como una sola consulta.
- No supongas que viene el teléfono. Los payloads nuevos pueden traer `business_scoped_user_id` en vez de `phone_number`.
- Kapso puede reintentar un envío. Usa el id del mensaje como nombre de la tarea en Cloud Tasks: así una tarea repetida se rechaza sola.

## Responder

Usa `@kapso/whatsapp-cloud-api` a través del proxy de Kapso:

```ts
import { WhatsAppClient } from "@kapso/whatsapp-cloud-api";

const client = new WhatsAppClient({
  baseUrl: "https://app.kapso.ai/api/meta/",
  kapsoApiKey: process.env.KAPSO_API_KEY!,
});

await client.messages.sendText({ phoneNumberId: process.env.KAPSO_PHONE_NUMBER_ID!, to, body });
```

Cómo escribir la respuesta:

- Si el agente devuelve `kind: "question"` (onboarding), manda solo la pregunta.
- Si devuelve un resultado, primero va el mejor precio: dónde, cuánto, en qué moneda, de cuándo es y qué tan confiable es el comercio.
- Después, como mucho otras dos opciones.
- Al final, un enlace a `usaprais.com/p/<slug>` con la comparación completa. Eso también trae tráfico a la web.
- Si el resultado quedó en revisión humana, dilo: "Estamos confirmando el precio con el comercio".
- Mensajes cortos, con el formato de WhatsApp (`*negrita*`). Nada de tablas.

## Variables

`KAPSO_API_KEY`, `KAPSO_WEBHOOK_SECRET`, `KAPSO_PHONE_NUMBER_ID`, `AGENT_URL`, `TASKS_QUEUE`. En GCP van en Secret Manager.

## Docs de Kapso

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Entrega: buffering, orden y reintentos](https://docs.kapso.ai/docs/platform/webhooks/advanced)
- [SDK de TypeScript](https://docs.kapso.ai/docs/whatsapp/typescript-sdk/introduction.md)
- [Índice completo para LLMs](https://docs.kapso.ai/llms.txt)
