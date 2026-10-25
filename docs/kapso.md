# WhatsApp con Kapso

El webhook y la respuesta están en `services/api/app/routes/whatsapp.py`. El carrusel está en `services/api/app/agents/listing.py`. La cola está en [gcp.md](gcp.md).

Desde afuera la ruta es `https://usaprais.com/api/whatsapp` (la web reenvía `/api/*`), o `<url de prais-api>/whatsapp` en Cloud Run.

## Configurar en Kapso

Kapso exige que el webhook responda en menos de 10 segundos. Por eso la ruta responde 200 y el trabajo sigue en la cola.

1. Crea un webhook de WhatsApp para el número, apuntando a `https://usaprais.com/api/whatsapp`, con el evento `whatsapp.message.received` y la versión 2 del payload.
2. Copia el secreto del webhook a `KAPSO_WEBHOOK_SECRET` y la API key del proyecto a `KAPSO_API_KEY`. En local van en `services/api/.env`; en producción, en el secreto `prais-api-secrets` (`infra/40-secrets.sh`).
3. Opcional: activa el buffering (5 segundos), para que los mensajes seguidos de una persona lleguen juntos.

## Qué lee el agente

El texto de la persona llega al agente tal cual, junto con lo que esa conversación ya dijo. La sesión es la de ADK (`whatsapp:{número}`): los turnos quedan en los eventos, y un nombre concreto queda en `session.state` como apunte (`product`). Un mensaje que no nombra un producto no borra ese apunte. "El último" no se convierte en una frase para buscar.

Varias burbujas seguidas son un turno. El webhook espera un silencio corto (`QUIET_S`, 1,5 s, tope 4 s) antes de llamar al agente, y un mensaje que llega mientras se arma la respuesta se suma a ese mismo turno. Kapso puede bufferar 5 segundos además; no hace falta para que esto funcione.

Cuando empieza el turno, el webhook marca el mensaje como leído y muestra que Prais está escribiendo (`typing_indicator` en el POST de mensajes de Kapso). Eso no es una tool del agente: si el modelo enviara el WhatsApp, se saltaría las tarjetas. El agente no tiene tools de Kapso. La historia del hilo ya está en la sesión de ADK; pedirla otra vez a Kapso solo agrega una vuelta.

Hay dos recetas. Si el mensaje trae un link, se lee el nombre del producto en esa página y se compara ese nombre: no se vuelve a preguntar cuál modelo es. Si la persona empieza de cero y el nombre ya se puede buscar, se busca. Si es vago y el hilo tampoco lo dijo, el agente pregunta una sola cosa, en una frase. La misma pregunta no se manda dos veces. Una duda ("el 17 o el 18", "el último") no se busca como si fuera el nombre del producto.

No hay una lista de modelos armada en el código. Si el agente pregunta, la pregunta sale en texto. Cuando hay dos o más ofertas con precio, la respuesta es el carrusel. Cuando hay una sola, es una tarjeta con el botón para abrirla. El producto de la conversación queda en el estado de la sesión de ADK (`product`). Un mensaje que llega después ("el último", "el que salió") no borra ese producto y no dispara "¿cuál modelo buscas?".

## Carrusel de la comparación

Cuando el producto ya está exacto, la respuesta es un carrusel (`carousel_message` en `services/api/app/agents/listing.py`). WhatsApp acepta de 2 a 10 tarjetas. Prais manda hasta cinco: las más baratas que publican un precio.

Una fila sin precio no ocupa un lugar. Si hay ofertas reales con precio, las de ejemplo no se usan para llegar a cinco. Siguen marcadas como ejemplo y solo entran cuando no hay ninguna real con precio. Si hay menos de cinco, salen las que hay. Con una sola se manda una tarjeta con botón, no un párrafo. Con ninguna, se manda el texto. No se inventan precios para completar las cinco.

## Pendiente

- Si un mensaje no trae `from` (los payloads nuevos pueden traer solo `business_scoped_user_id`), hoy se ignora.
- Un reintento de la tarea reenvía la respuesta ya guardada (por id de mensaje) y no vuelve a correr el agente. Si el intento anterior sigue dentro de 120 s, la cola espera.

## Docs

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Eventos de mensajes](https://docs.kapso.ai/docs/platform/webhooks/message-events.md)
- [Enviar texto](https://docs.kapso.ai/docs/whatsapp/send-messages/text.md)
