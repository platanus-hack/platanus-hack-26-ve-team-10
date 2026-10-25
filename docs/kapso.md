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

Cuando empieza el turno, el webhook marca el mensaje como leído y muestra que Prais está escribiendo (`typing_indicator` en el POST de mensajes de Kapso). WhatsApp apaga ese indicador al enviar un mensaje **o a los ~25 segundos**, y una búsqueda puede pasar de eso, así que se vuelve a emitir cada 20 s mientras el agente trabaja (`_keep_typing`): mandarlo una sola vez deja a la persona viendo el indicador apagarse, que es peor que no ponerlo. Si falla, se sigue sin él. Eso no es una tool del agente: si el modelo enviara el WhatsApp, se saltaría las tarjetas. El agente no tiene tools de Kapso. La historia del hilo ya está en la sesión de ADK; pedirla otra vez a Kapso solo agrega una vuelta.

Hay dos recetas. Si el mensaje trae un link, se lee el nombre del producto en esa página y se compara ese nombre: no se vuelve a preguntar cuál modelo es. Si la persona empieza de cero y el nombre ya se puede buscar, se busca. Si es vago y el hilo tampoco lo dijo, el agente pregunta una sola cosa, en una frase. La misma pregunta no se manda dos veces. Una duda ("el 17 o el 18", "el último") no se busca como si fuera el nombre del producto. Si el resumen del modelo falla después de una búsqueda, igual salen las tarjetas que ya se encontraron.

No hay una lista de modelos armada en el código. Si el agente pregunta, la pregunta sale en texto. Cuando hay dos o más ofertas con precio, la respuesta es el carrusel. Cuando hay una sola, es una tarjeta con el botón para abrirla. El producto de la conversación queda en el estado de la sesión de ADK (`product`). Un mensaje que llega después ("el último", "el que salió") no borra ese producto y no dispara "¿cuál modelo buscas?".

## El acuse: qué se entendió, antes de buscar

Una búsqueda puede tardar 45 segundos. Hasta ahora, lo primero que la persona leía era el carrusel, así que si Prais entendió mal el producto se enteraba 45 segundos tarde, con el minuto ya perdido.

El acuse no lo decide un regex ni un catálogo: lo decide **el modelo, y gratis**. Si va a buscar, llama a una tool `find_listings_` y el argumento `product` es su lectura del producto; si va a preguntar, no hay llamada y su pregunta ya sale rápido. Esa llamada aparece en el primer turno, a uno o dos segundos, mucho antes del scraping. `_event_search_call` la lee en el flujo de eventos y `searched_name` le quita el arranque de intención ("comprar un iphone 17pro" se acusa como "iphone 17pro"); lo que no calce pasa igual, porque no es una lista de productos.

> Dale! Busco **iPhone 17 Pro** y te digo dónde está más barato. Si no es ese, dime cuál.

Promete lo que Prais hace, no lo que va a encontrar: decir "te traigo lo más confiable" antes de buscar es prometer un resultado que puede no existir, y el personaje tiene prohibido exagerar ([design-system/prais.md](design-system/prais.md)). La segunda frase es la que vale: deja corregir mientras todavía sirve, y esa corrección ya la recoge el bucle, que descarta la respuesta a medio hacer y rehace la búsqueda con lo nuevo.

Sale **a los 1,5 segundos de la llamada, y se cancela si la respuesta llega antes**. La web abierta cachea una hora el mismo producto, así que repetir una búsqueda vuelve instantánea: sin esa gracia se gastaría un mensaje para nada, y en WhatsApp cada mensaje cuenta contra el plan. Se acusa una sola vez aunque corran varias fuentes, y si el envío falla se sigue sin él.

El canal lo pasa como `on_search` a `ask_prais`: el agente no sabe de Kapso y la web no manda acuse.

## El resultado y la salida

El cuerpo lleva arriba, en negrita, **el producto con el que se buscó de verdad** (`_result_body`). Lo que la conversación fue fijando turno a turno no se veía en ningún lado: si quedó mal, la persona se enteraba al leer tarjetas de otra cosa. Solo se encabeza así cuando alguna fuente llegó a contestar: un saludo no lleva producto.

**Cada tarjeta** muestra el puntaje de confianza en estrellas de 0 a 5, no el entero de 0 a 100 ("Confianza 80" no dice sobre qué), y **la fecha en que se vio el precio**: con esta inflación, un precio sin fecha no es un precio (regla 7).

Después del resultado va un mensaje aparte con hasta tres botones, porque WhatsApp no deja colgarlos de un carrusel:

- **Con precios**, y solo si las ofertas mezclan usados y nuevos, "Solo nuevos" y "Solo usados". El filtro sale de lo que trajeron las ofertas, no de un catálogo: así vale para un teléfono y para un carro sin saber de cuál se trata.
- **Sin precios**, se ofrece soltar lo que sobra: "Sin la capacidad", "Nuevos y usados". Solo se quitan palabras que la persona escribió, así que nunca se inventa un atributo que nadie nombró. Si no hubo nada que mostrar, el texto además dice qué no se encontró.
- **Si la búsqueda se cae**, la consulta no se pierde: "Reintentar".

Un botón vuelve **solo con su título**, sin el producto. Por eso lo ofrecido se guarda en la tabla `dialogs` (`app/lib/dialog.py`), en la misma base que las sesiones: Cloud Run corre varias copias de `prais-api`, así que la respuesta sale de una y el toque entra por otra. Sin eso, "Solo nuevos" se buscaría como si fuera un producto. Sin `SESSION_DATABASE_URL` queda en memoria, y un diálogo de más de 24 horas se ignora, que es la ventana en la que WhatsApp deja contestar libre.

## La comparación: lista o carrusel

Hay **dos formas de contestar la comparación y se elige una**, con `WHATSAPP_REPLY_STYLE`. Las dos viven en `services/api/app/agents/listing.py` y `shopping_message` despacha entre ellas.

| Valor | Función | Qué manda |
|---|---|---|
| `list` (por defecto) | `list_message` | Texto: el veredicto y una viñeta por oferta con precio, vendedor, detalle y el enlace de la tienda |
| `carousel` | `carousel_or_card` | El carrusel de tarjetas con foto, o una tarjeta con botón si solo hay una oferta |

**Por qué la lista es lo de hoy.** La tarjeta lleva imagen obligatoria y, cuando el anuncio trae foto, se le pasa a WhatsApp la URL de la tienda tal cual. Meta rechaza algunos formatos y devuelve un `400` que tumba el mensaje entero:

```
(#131053) Media upload error — WebP image uploads are not currently supported.
```

Pasaba en cerca del 14 % de los turnos y se perdía la respuesta completa. La lista no depende del formato que sirva cada tienda. El carrusel queda entero: cuando las fotos pasen por nuestro propio JPEG, se vuelve a encender con `WHATSAPP_REPLY_STYLE=carousel`.

La lista tampoco tiene mínimo de dos: con una sola oferta sale igual, y ahí no hace falta la tarjeta suelta. Los enlaces van sin vista previa (`preview_url: false`), porque con cinco WhatsApp expandiría el primero y descuadraría el mensaje.

## El carrusel

Cuando el producto ya está exacto, la respuesta es un carrusel (`carousel_message`). WhatsApp acepta de 2 a 10 tarjetas. Prais manda hasta cinco: las más baratas que publican un precio.

Cada tarjeta lleva imagen obligatoria. Si el anuncio no trae foto, Prais usa una del producto marcada «imagen de Prais» (`services/api/app/agents/card_image.py`). Esas fotos van al bucket de Cloud Storage y se sirven desde `GET /card-images/{token}.jpg`: ver [gcp.md](gcp.md#almacenamiento).

Una fila sin precio no ocupa un lugar. Si hay ofertas reales con precio, las de ejemplo no se usan para llegar a cinco. Siguen marcadas como ejemplo y solo entran cuando no hay ninguna real con precio. Si hay menos de cinco, salen las que hay. Con una sola se manda una tarjeta con botón, no un párrafo. Con ninguna, se manda el texto. No se inventan precios para completar las cinco.

## Cuando el turno no sale bien

Un turno nunca puede terminar en silencio: la cola ya dio la tarea por hecha y la persona se queda con el indicador de «escribiendo» encendido para siempre.

| Si pasa | Qué hace Prais |
|---|---|
| El agente se cuelga | `TURN_TIMEOUT_S` (120 s por defecto) corta y sale un aviso pidiendo el producto otra vez. Antes, el único tope eran los 300 s de Cloud Run, que mataban la request sin contestar nada |
| Kapso rechaza el carrusel | El `400` se loguea con su cuerpo, que es el que dice qué campo fue, y el veredicto sale en texto plano. Antes se perdía la respuesta entera |

`replies.LEASE_SECONDS` (240 s) tiene que quedar **por encima** de `TURN_TIMEOUT_S` más lo que tarde el envío. Si vence antes, el reintento de la cola se lleva la reserva de un turno que todavía corre, lo da por hecho con un `200` y esa respuesta ya no se reintenta nunca.

## Pendiente

- Si un mensaje no trae `from` (los payloads nuevos pueden traer solo `business_scoped_user_id`), hoy se ignora.
- Un reintento de la tarea reenvía la respuesta ya guardada (por id de mensaje) y no vuelve a correr el agente. Si el intento anterior sigue dentro del plazo (`replies.LEASE_SECONDS`), la cola espera.

## Docs

- [Webhooks](https://docs.kapso.ai/docs/platform/webhooks/overview)
- [Seguridad de los webhooks](https://docs.kapso.ai/docs/platform/webhooks/security.md)
- [Eventos de mensajes](https://docs.kapso.ai/docs/platform/webhooks/message-events.md)
- [Enviar texto](https://docs.kapso.ai/docs/whatsapp/send-messages/text.md)
