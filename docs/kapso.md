# WhatsApp con Kapso

El webhook y la respuesta están en `services/api/app/routes/whatsapp.py`. El carrusel está en `services/api/app/agents/listing.py`. La cola está en [gcp.md](gcp.md).

Desde afuera la ruta es `https://usaprais.com/api/whatsapp` (la web reenvía `/api/*`), o `<url de prais-api>/whatsapp` en Cloud Run.

## Configurar en Kapso

Kapso exige que el webhook responda en menos de 10 segundos. Por eso la ruta responde 200 y el trabajo sigue en la cola.

1. Crea un webhook de WhatsApp para el número, apuntando a `https://usaprais.com/api/whatsapp`, con el evento `whatsapp.message.received` y la versión 2 del payload.
2. Copia el secreto del webhook a `KAPSO_WEBHOOK_SECRET` y la API key del proyecto a `KAPSO_API_KEY`. En local van en `services/api/.env`; en producción, en el secreto `prais-api-secrets` (`infra/40-secrets.sh`).
3. Opcional: activa el buffering (5 segundos), para que los mensajes seguidos de una persona lleguen juntos.

## Qué lee el agente

El texto de la persona llega al agente. Un toque en una lista vieja también: Kapso lo manda como `interactive` con `list_reply.title` (y `button_reply.title` para un botón). Ese título es el mensaje.

Hay dos recetas. Si el mensaje trae un link, se lee el nombre del producto en esa página y se compara ese nombre: no se vuelve a preguntar cuál modelo es. Si la persona empieza de cero y el nombre ya se puede buscar, se busca. Si es vago, el agente pregunta una sola cosa, en una frase. La misma pregunta no se manda dos veces: a la segunda, se busca con lo que la persona ya dijo.

No hay una lista de modelos armada en el código. Si el agente pregunta, la pregunta sale en texto. Cuando hay dos o más ofertas con precio, la respuesta es el carrusel. Cuando hay una sola, es una tarjeta con el botón para abrirla. El producto de la conversación queda en el estado de la sesión de ADK (`product`). Un mensaje que llega después ("el último", "el que salió") no borra ese producto y no dispara "¿cuál modelo buscas?".

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
