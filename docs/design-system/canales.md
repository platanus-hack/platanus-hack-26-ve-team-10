# Canales

usaprais responde donde ya está la persona y usa el formato nativo de cada canal. El contenido es siempre el mismo —la lista ordenada del más barato al más caro, con información para decidir—; cambia cuánto controla la marca.

| Canal | Formato | Qué controla la marca | Componente |
|---|---|---|---|
| Web (usaprais.com) | Experiencia completa | Todo: color, tipografía, Prais animado, ranking interactivo | `SearchBox`, `PriceRange`, `RankedList`, `FichaOferta` |
| WhatsApp | Flow o mensaje | Solo el texto y las imágenes; la interfaz es de WhatsApp | `MensajeCanal canal="whatsapp"` |
| X | Respuesta en el hilo | Texto de 280 caracteres, una imagen opcional | `MensajeCanal canal="x"` |
| Instagram | Carrusel por DM + texto | El carrusel completo y un DM corto | `IGSlide`, `MensajeCanal canal="instagram"` |

## Web

Es donde la marca se luce. Orden de la pantalla de resultado: `PraisSays` con el resumen en una frase → `PriceRange` si la persona trajo un precio → `RankedList`. Todo en una columna de máximo 760px.

Al tocar una oferta se abre `FichaOferta`. Los anuncios de Marketplace, Mercado Libre o Instagram se muestran siempre con la estética de usaprais (nunca imitando la plataforma de origen) y "Ir al anuncio" lleva al anuncio original. El recorrido completo en el teléfono está en `PantallasMovil`.

## WhatsApp

- El texto sale de `Prais.textoParaCanal('whatsapp', datos)`: producto en negrita, hasta 5 precios con tienda en negrita, una línea de contexto por oferta y el enlace a la lista completa.
- En un Flow, cada oferta es una opción de la lista: título = tienda, descripción = total y Bs., metadata = canal · condición · envío.
- La foto de perfil de la cuenta es Prais `tranqui` en su círculo (`prais-tranqui-circulo.svg`).

## X

- Una sola respuesta, sin hilo propio. `textoParaCanal('x', datos)` la corta en 280 caracteres.
- Si adjuntas imagen, usa el slide de oferta #1 (`IGSlide tipo="oferta"`).
- La foto de perfil es la misma que en WhatsApp.

## Instagram

- Carrusel de hasta 7 slides de 1080 × 1350: 1 portada + hasta 5 ofertas + 1 cierre.
- El DM que lo acompaña (`textoParaCanal('instagram', datos)`) repite la oferta #1 en texto, para quien no abre el carrusel y para lectores de pantalla.
- Los slides siempre en tema papel.
