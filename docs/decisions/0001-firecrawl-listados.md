# 0001. Cómo lee Firecrawl los listados y los portales de anuncios

Issue [#55](https://github.com/platanus-hack/platanus-hack-26-ve-team-10/issues/55). Cierra la decisión abierta 4 de [resources/queries.md](../../resources/queries.md#6-decisiones-de-política-abiertas).

## Contexto

La web abierta (`apps/api/app/lib/sources/firecrawl.py`) leía cada página con el formato `product` de Firecrawl: un solo producto, sacado de los datos estructurados de la página (JSON-LD, microdatos, OpenGraph), sin un modelo de lenguaje. Funciona en la ficha de un producto, pero no en un listado ni en un portal de anuncios. Con "Chevrolet Aveo usado" no salía ningún precio, aunque Autocosmos muestra 6 Aveo con precio.

En el PR #46 no quedó escrito por qué se usó `product` y no una extracción JSON: la primera versión del archivo ya lo usaba. El eval de Firecrawl que se hizo antes (método C: búsqueda y extracción JSON de una lista de ofertas) era justamente lo que propone el issue.

Medido el 24 de octubre de 2026, con los créditos que reporta Firecrawl en cada respuesta:

| Formato | Créditos por página | Tiempo | En un listado |
|---|---|---|---|
| `product` | 1 | 1 a 2 s | Nada: "No product found on this page" |
| JSON con schema (lista de ofertas), más `markdown` | 5 (el markdown no cobra aparte) | 5 a 20 s | Una oferta por anuncio, con su link |

## Opciones consideradas

1. **Solo `product`.** Barato y determinista, pero no lee listados ni portales: los carros, las motos y lo usado quedan sin precio.
2. **Solo JSON.** Lee todo, pero cuesta 5 veces más en cada página, tarda más y pasa por un modelo, que puede inventar un precio o mezclar productos.
3. **`product` primero y JSON solo si no hubo precio.** Las fichas que ya funcionaban siguen costando 1 crédito y salen igual. Los listados pagan la extracción.

## Decisión

La opción 3, con controles sobre lo que devuelve el modelo:

- **El precio tiene que estar escrito en la página.** Se pide también el markdown, y una oferta solo vale si su monto aparece en él.
- **La moneda la dice la página.** Se toma el símbolo escrito junto al monto (`u$s`, `REF`, `$`, `Bs.`), no la etiqueta del modelo, que a veces marca como Bs un precio en REF. `u$s`, `U$S` y `REF` cuentan como USD.
- **Cada oferta del listado tiene que ser el producto pedido.** Su título tiene que nombrar la marca, el modelo y las cifras de la consulta (en singular, y sin exigir categorías ni unidades que cada tienda escribe a su manera). Un listado de harinas trae Kaly y Juana además de PAN, y uno de Redmi trae el 13C además del 15C.
- **Un listado no llena la respuesta solo.** Hasta 2 ofertas por tienda; si con eso no se llega a 5, se completa con las más baratas que quedaron fuera.
- **TuCarro, Trovit y eBay no se leen.** TuCarro es de Mercado Libre y pide una verificación anti-bots: le toca al especialista de Mercado Libre, y no se intenta saltarla. Trovit junta anuncios de otros portales, da links de rastreo, marca en Bs precios en dólares y tarda unos 40 s. Tampoco eBay, que es de Estados Unidos.
- **Lo que falla se ve.** `firecrawl:<dominio>` aparece una vez por dominio cuando una página suya quedó bloqueada, dio error o no terminó a tiempo, y ese dominio no tiene ofertas en la respuesta; un link muerto (404 o 410) no cuenta. Cada consulta deja una línea de log (`prais.firecrawl`) con el resultado, el tiempo y los créditos de cada página.

**Consecuencias.** En la prueba con las 12 consultas de [resources/queries.md](../../resources/queries.md), las ofertas con precio pasaron de 16 a 41, y los créditos de las páginas, de unos 4 a unos 16 por consulta (más 2 de la búsqueda). De las ofertas que se perdieron, las que no quedaron fuera por el tope de 5 eran de otro producto: el formato `product` había leído un producto relacionado de la página (una chicha en la ficha de un arroz, un iPhone 16 en la de un iPhone 13). La cache de 1 hora por producto sigue siendo el principal ahorro. Que la oferta sea exactamente el producto pedido (Pro contra no Pro, nuevo contra usado) sigue abierto en #54.
