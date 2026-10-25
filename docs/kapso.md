# WhatsApp con Kapso

El webhook y la respuesta están en `services/api/app/routes/whatsapp.py`. El carrusel está en `services/api/app/agents/listing.py`. La cola está en [gcp.md](gcp.md).

Desde afuera la ruta es `https://usaprais.com/api/whatsapp` (la web reenvía `/api/*`), o `<url de prais-api>/whatsapp` en Cloud Run.

## Configurar en Kapso

Kapso exige que el webhook responda en menos de 10 segundos. Por eso la ruta responde 200 y el trabajo sigue en la cola.

1. Crea un webhook de WhatsApp para el número, apuntando a `https://usaprais.com/api/whatsapp`, con el evento `whatsapp.message.received` y la versión 2 del payload.
2. Copia el secreto del webhook a `KAPSO_WEBHOOK_SECRET` y la API key del proyecto a `KAPSO_API_KEY`. En local van en `services/api/.env`; en producción, en el secreto `prais-api-secrets` (`infra/40-secrets.sh`).
3. Opcional: activa el buffering (5 segundos), para que los mensajes seguidos de una persona lleguen juntos.

## Lista para precisar el producto

Si el nombre todavía deja una elección que cambia el precio, Prais pregunta una sola cosa y no busca. En WhatsApp esa pregunta sale como lista: el cuerpo es la pregunta y cada fila es una opción. Para un iPhone 14 las filas son iPhone 14, iPhone 14 Plus, iPhone 14 Pro, iPhone 14 Pro Max y Me da igual. El botón dice "Ver opciones".

La persona puede tocar una fila o contestar con texto. El texto se lee como siempre, en `message.text.body`. Un toque llega como mensaje `interactive`. Kapso documenta ese sobre para `button_reply` (`interactive.button_reply.title`); la fila de una lista usa el mismo sobre con `interactive.type` `list_reply` y `list_reply.title`.

La forma del envío es la de [Enviar listas](https://docs.kapso.ai/docs/whatsapp/send-messages/lists.md): `type: interactive`, `interactive.type: list`, `body.text`, `action.button` y `action.sections[].rows[]` con `id` y `title`. Se manda al mismo endpoint de mensajes, con `X-API-Key`. La arma `list_message` en `services/api/app/agents/listing.py` y la envía `services/api/app/routes/whatsapp.py`. Si la lista falla, la misma pregunta se manda en texto.

```json
{
  "messaging_product": "whatsapp",
  "to": "584120000000",
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": { "text": "¿Cuál iPhone 14 buscas?" },
    "action": {
      "button": "Ver opciones",
      "sections": [
        {
          "title": "Modelos",
          "rows": [
            { "id": "iphone-14", "title": "iPhone 14" },
            { "id": "iphone-14-plus", "title": "iPhone 14 Plus" },
            { "id": "iphone-14-pro", "title": "iPhone 14 Pro" },
            { "id": "iphone-14-pro-max", "title": "iPhone 14 Pro Max" },
            { "id": "me-da-igual", "title": "Me da igual" }
          ]
        }
      ]
    }
  }
}
```

## Carrusel de la comparación

Cuando el producto ya está exacto, la respuesta es un carrusel (`carousel_message` en `services/api/app/agents/listing.py`). WhatsApp acepta de 2 a 10 tarjetas. Prais manda hasta cinco: las más baratas que publican un precio.

Una fila sin precio no ocupa un lugar. Si hay ofertas reales con precio, las de ejemplo no se usan para llegar a cinco. Siguen marcadas como ejemplo y solo entran cuando no hay ninguna real con precio. Si hay menos de cinco, salen las que hay. Con una sola, o con ninguna, no se arma el carrusel, porque WhatsApp exige al menos dos tarjetas, y se manda el texto. No se inventan precios para completar las cinco.

## Pendiente

- Si un mensaje no trae `from` (los payloads nuevos pueden traer solo `business_scoped_user_id`), hoy se ignora.
- Un reintento de la tarea reenvía la respuesta ya guardada (por id de mensaje) y no vuelve a correr el agente. Si el intento anterior sigue dentro de 120 s, la cola espera.

## Docs

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Eventos de mensajes](https://docs.kapso.ai/docs/platform/webhooks/message-events.md)
- [Enviar texto](https://docs.kapso.ai/docs/whatsapp/send-messages/text.md)
- [Enviar listas](https://docs.kapso.ai/docs/whatsapp/send-messages/lists.md)
