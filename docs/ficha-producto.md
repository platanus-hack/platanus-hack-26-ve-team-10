# Ficha de producto

La página de un modelo con todas sus ofertas. Es la que más tráfico orgánico puede traer: en Venezuela la gente busca el modelo ("iphone 17", 40.500 búsquedas al mes; "redmi 15c", 22.200), no la categoría ("televisores", 3.600). Los datos están en [resources/keywords-ve.md](../resources/keywords-ve.md).

Este doc es la referencia viva de la ficha: si cambia una decisión, se cambia aquí por PR.

## URL

```
/ve/p/iphone-17-pro-max-k8f2/
/ve/p/redmi-15c-x3a9/
/ve/p/bera-br-200-m7q1/
```

- **Prefijo de país `/ve/`.** Venezuela es el primer mercado; otro país entra como `/co/`, `/mx/`, sin mover nada. Reemplaza el `/p/[slug]` de [docs/seo-geo.md](../docs/seo-geo.md).
- **El slug es el modelo tal como lo busca la gente:** "iphone-17", no "apple-iphone-17"; "redmi-15c", no "xiaomi-redmi-15c". La marca va delante solo si el modelo solo es ambiguo (`bera-br-200`).
- **El slug termina en un id corto (`-k8f2`).** Los nombres que trae una fuente cambian; el id no. Si el slug cambia, la URL vieja redirige 301 a la nueva usando el id.
- **Sin "precio" en la URL.** Solo ~2,4% de las búsquedas lo escriben; va en el title.
- **Capacidad y color son variantes dentro de la ficha**, no fichas aparte: `?capacidad=256gb&color=negro`, con `noindex` y `canonical` a la ficha. Igual los filtros de la tabla (`?ciudad=`, `?pago=`, `?condicion=`).

## Title, description y H1

```
Title:       iPhone 17 Pro Max: precio en Venezuela hoy desde $1.299 (Bs 52.025) | Prais
Description: Compara el iPhone 17 Pro Max en 7 comercios de Venezuela. Nuevo desde $1.299, usado desde $980. Precios en USD y bolívares a tasa BCV, actualizados hace 2 h.
H1:          iPhone 17 Pro Max
Bajo el H1:  Desde $1.299 en 7 comercios · Actualizado hace 2 h · Tasa BCV 40,05 (24 oct)
```

El precio "desde" es siempre el del producto **nuevo**. Si el modelo solo tiene ofertas usadas, el title dice "usado desde".

## Bloques, en orden

1. **Respuesta primero (GEO).** Un párrafo que contesta la pregunta con fuente y fecha: "El iPhone 17 Pro Max cuesta desde $1.299 nuevo en Venezuela, visto el 24 de octubre en Daka. Usado, desde $980." Se genera con los datos de la ficha.
2. **Resumen de precio.** Nuevo desde (USD y Bs), usado desde, reacondicionado desde, rango, cantidad de comercios, hora de actualización y la tasa usada con su fuente y fecha.
3. **Tabla de ofertas.** El corazón de la página. Pestañas **Nuevo / Usado / Reacondicionado** (abre en Nuevo) y filtros de ciudad y método de pago.

   | Comercio | Confianza | Precio USD | Bs | Variante | Ciudad / envío | Pagos | |
   |---|---|---|---|---|---|---|---|
   | Daka | 92 | $1.299 | Bs 52.025 | 256 GB · Negro | Caracas · envío nacional | Zelle · Pago móvil · Cashea | Ir al comercio |

   - Ordenadas por precio en USD, como devuelve `search_offers`.
   - Ofertas con `price: null` ("precio al DM") van al final, sin precio y con el enlace para consultarlo. No cuentan para el "desde".
   - La confianza se muestra como dato, sin enlace: por ahora no hay página de comercio.
   - Una oferta sale de la tabla si lleva más de 48 h sin aparecer en un rastreo; queda en el historial.
4. **Historial de precio.** Gráfico del precio mínimo nuevo en USD. Se muestra con 14 días o más de datos; con 30 días o más agrega un veredicto: "Está 8% por debajo de su promedio de 30 días". Es el contenido que nadie puede copiar y crece solo.
5. **Variantes.** Capacidades y colores, cada uno con su precio mínimo.
6. **Especificaciones clave.** De 6 a 10 datos normalizados. No se copia la descripción del fabricante.
7. **Alternativas.** Modelos de la misma categoría y rango de precio. Es enlazado interno y la semilla de futuras páginas "X vs Y".
8. **Preguntas frecuentes respondidas con datos.** "¿Cuánto cuesta el iPhone 17 Pro Max en Venezuela?", "¿Dónde está más barato?", "¿Cuánto es en bolívares?", "¿Cuánto cuesta usado?". Las respuestas salen de los datos del momento.
9. **Breadcrumbs.** Teléfonos › Apple › iPhone 17 Pro Max.

## Schema

- `Product` con `AggregateOffer`: `lowPrice`, `highPrice`, `offerCount`, `priceCurrency: "USD"`, calculados **solo con las ofertas nuevas** y `itemCondition: NewCondition`. Si solo hay usadas, se usan esas con `UsedCondition`.
- Google acepta una sola moneda por oferta: el precio en bolívares va solo como texto visible.
- `BreadcrumbList`.
- `FAQPage` no da rich results a sitios como este desde 2023. Las preguntas van igual en la página, por su valor para GEO; el JSON-LD es opcional.

## Que miles de fichas no parezcan iguales

- El valor está en los datos propios: ofertas, historial y conversión a bolívares. Nada de texto copiado del fabricante.
- El párrafo de respuesta y las preguntas frecuentes se generan con datos, así que cambian en cada ficha y en cada actualización.
- Se indexa una ficha con al menos una oferta con precio.

## Ciclo de vida

- **Sin ofertas, la ficha no se borra.** "iphone 11" sigue teniendo 14.800 búsquedas al mes. Muestra el último precio visto con su fecha, el historial y alternativas.
- Pasa a `noindex` solo si no tiene ofertas **y** no tiene demanda de búsqueda.
- Si un modelo tiene sucesor directo, se enlaza arriba: "Ya salió el iPhone 18".

## Qué datos necesita (cambios de contrato)

Lo de abajo no existe todavía en `services/api/app/lib/types.py`. Cambiar un contrato se avisa al equipo antes de mergear ([docs/contracts.md](../docs/contracts.md)).

| Dato | Dónde | Para qué |
|---|---|---|
| `condition: "new" \| "used" \| "refurbished"` | `Offer` | Pestañas y el "desde" de nuevo |
| `variant?: { capacity?, color? }` | `Offer` | Bloque de variantes y filtros |
| `paymentMethods?: string[]` | `Merchant` (o `Offer` si varía) | Columna y filtro de pagos |
| `productId` | Nuevo: el modelo al que pertenece una oferta | Juntar ofertas de varias fuentes en una ficha |
| Historial: una fila por oferta y rastreo (`productId`, `merchantId`, precio USD, precio Bs, tasa, condición, `seenAt`) | Almacenamiento nuevo | Gráfico y veredicto. Se guarda **desde el día uno**: no se puede reconstruir después |

## Decisiones abiertas

- **Tasa:** BCV, paralela o ambas está abierto en [docs/architecture.md](../docs/architecture.md). Este doc asume BCV para el precio en Bs, porque es lo que más se busca ("dolar bcv", 4,09 millones de búsquedas al mes).
- **Perfil de comercio:** pospuesto. Si se hace, iría en `/ve/comercios/[slug]` y la confianza pasaría a enlazar ahí.
