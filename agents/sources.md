# Fuentes

Cada fuente es un archivo en `apps/api/app/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). Hoy solo existe la de ejemplo (`mock.py`), que se apaga con `USE_MOCK_SOURCE=false`. Además de sus ofertas fijas, la de ejemplo responde por cada modelo del catálogo (`catalogo.json`) con comercios marcados "(ejemplo)" y precios generados desde `precioEjemplo`. Apagarla deja el catálogo con solo ofertas reales: ver [seo-geo.md](seo-geo.md#catálogo-el-interruptor-de-indexación).

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | SDK de Python de Firecrawl: `search`, `scrape` y extracción con schema (confirma el paquete en su `llms.txt`) | Cobra por uso. El puntaje de confianza de tiendas web también lo usa (ver [resources/website-trust-score.ts](../resources/website-trust-score.ts)) |
| **Apify: Instagram** | Cliente de Python de Apify + actor `apify/instagram-scraper` | Tarda de segundos a minutos. Muchas tiendas ponen "precio al DM": la oferta va con `price=None` |
| **Apify: TikTok** | Cliente de Python de Apify + actor `clockworks/tiktok-scraper` | Igual que Instagram. El puntaje de confianza usa `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper` (ver [resources/tiktok-trust-score.ts](../resources/tiktok-trust-score.ts)) |
| **Apify: Facebook Marketplace** | Cliente de Python de Apify + un actor de Marketplace de la Apify Store | Facebook no tiene API oficial. Candidato: `deepmine/facebook-marketplace-scraper`, con proxy residencial (ver [resources/fb-marketplace-trust-score.ts](../resources/fb-marketplace-trust-score.ts)) |
| **Mercado Libre** | API oficial, sitio `MLV` | Responde **403 sin token**: hay que registrar una app. Plan B: un actor de Apify. El puntaje de confianza usa `/items` y `/users` (ver [resources/mercadolibre-trust-score.ts](../resources/mercadolibre-trust-score.ts)) |
| **Meta Ads** | API de la Ad Library | Solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Para Venezuela no sirve. Candidato: el actor `curious_coder/facebook-ads-library-scraper`, que se usa para ajustar el puntaje de confianza (ver [resources/meta-ads-signals.ts](../resources/meta-ads-signals.ts)) |

## Reglas

- **Lento no va en vivo.** Cada fuente tiene 8 segundos (`asyncio.wait_for` la cancela). Si tarda más (Apify), el actor corre antes y el adapter lee su último resultado.
- **Sin precio no hay inventos.** Si la publicación no tiene precio, `price` va en `None`.
- **Una fuente que falla no tumba la búsqueda.** `search_offers` ya la deja fuera y la anota en `failedSources`.
- **Async de verdad.** `search` es `async`: usa clientes asíncronos (`httpx.AsyncClient`) para no bloquear a las demás fuentes.
- **Guarda los datos del comercio** (seguidores, comentarios, reputación), porque los usa el puntaje de confianza. Qué traer de cada fuente está en [Datos que el puntaje necesita](#datos-que-el-puntaje-necesita).

## Puntaje de confianza por fuente

Cada fuente tiene un borrador de su puntaje de confianza en `resources/`, en TypeScript. Ahí están las señales, los pesos, las banderas rojas y los actores o APIs que usa. La implementación va en Python en `apps/api/app/lib/prices.py`. Antes de portarlo, corre el actor con casos reales y confirma los nombres de sus campos.

| Fuente | Borrador | Qué pesa más |
|---|---|---|
| Instagram | [ig-trust-score.ts](../resources/ig-trust-score.ts) | Antigüedad de la cuenta, interacción acorde a los seguidores y comentarios reales |
| Facebook Marketplace | [fb-marketplace-trust-score.ts](../resources/fb-marketplace-trust-score.ts) | Historial del vendedor y fotos que no aparecen en anuncios de otros: en Venezuela casi nadie califica |
| TikTok | [tiktok-trust-score.ts](../resources/tiktok-trust-score.ts) | Proporción entre likes y vistas, no likes por seguidor: las vistas las reparte el algoritmo |
| Tiendas web | [website-trust-score.ts](../resources/website-trust-score.ts) | Antigüedad del dominio, RIF y contacto publicados, políticas de devolución |
| Mercado Libre | [mercadolibre-trust-score.ts](../resources/mercadolibre-trust-score.ts) | Reputación de la plataforma: termómetro, MercadoLíder y calificaciones |
| Amazon | [amazon-trust-score.ts](../resources/amazon-trust-score.ts) | Quién envía (Amazon, FBA o el vendedor) y el feedback del vendedor externo. Detecta cuentas inactivas que reaparecen con precios bajos |
| Meta Ads | [meta-ads-signals.ts](../resources/meta-ads-signals.ts) | No es un puntaje: ajusta el de Instagram, Marketplace o TikTok. Un vendedor que no anuncia no pierde nada |

Todos comparten la misma salida: puntaje de 0 a 100, cobertura, veredicto (`confiable`, `precaucion`, `riesgosa` o `sin_datos`), banderas rojas y razones. Una bandera roja deja el puntaje en 0. Si hay menos de 40 % del peso medido, el veredicto es `sin_datos`.

## Datos que el puntaje necesita

Hoy `Merchant` solo trae `followers`, `comments` y `response_time_min`. El puntaje de confianza solo cuenta las señales cuyo dato trae la fuente: las demás no se cuentan y su peso se reparte entre las que sí hay. Por eso, **cada dato de esta lista que traiga tu fuente suma una señal al puntaje** sin tocar nada más.

Cómo guardarlo:

- Como campo opcional de `Merchant` en `snake_case`, con `None` por defecto. Cambiar `types.py` es cambiar un contrato: avisa en el canal antes de mergear.
- Si la fuente no trae el dato, va `None`, nunca `0`. `None` no cuenta; `0` cuenta como dato malo.
- Fechas en ISO 8601, como `seen_at`. Listas de publicaciones: las más recientes primero, máximo 20.
- Lo lento (la sección "Información sobre esta cuenta" de Instagram, los comentarios, el historial del vendedor) va en el actor que corre antes, no en la consulta en vivo.

Los nombres de campo de origen son los de los borradores en `resources/`: confírmalos con una corrida real del actor antes de escribir el adapter. Los pesos de cada señal están en esos borradores, no aquí, para que no se desincronicen.

### Instagram

Actores: `apify/instagram-profile-scraper` y `apify/instagram-comment-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Fecha de creación de la cuenta | `about.dateJoined` (opción de pago "about" del actor) | Antigüedad; menos de 1 mes es bandera roja |
| Cambios de nombre de usuario | `about.formerUsernames` | Cambios de @; 4 o más es bandera roja |
| País de la cuenta | `about.country` | País coherente |
| Likes y comentarios por publicación | `latestPosts[].likesCount`, `commentsCount` | Interacción, consistencia y comentarios/likes |
| Fecha de cada publicación | `latestPosts[].timestamp` | Ritmo de publicación |
| Texto y autor de comentarios recientes (unos 30 de los 3 últimos posts) | `text`, `ownerUsername` del actor de comentarios | Calidad de comentarios |
| Bio y captions | `biography`, `latestPosts[].caption` | Lenguaje de riesgo |
| Cuenta privada | `private` | Se avisa al usuario |

### TikTok

Actores: `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| ID numérico del usuario | `authorMeta.id` (la fecha de creación sale de sus 32 bits altos) | Antigüedad; menos de 1 mes es bandera roja |
| Región | `authorMeta.region` | Región coherente |
| Likes totales de la cuenta | `authorMeta.heart` | Likes totales / seguidores |
| Por video: vistas, likes, compartidos, guardados, fecha y si es anuncio | `playCount`, `diggCount`, `shareCount`, `collectCount`, `createTimeISO`, `isAd` | Likes/vistas, consistencia, compartidos + guardados, ritmo |
| Texto y autor de comentarios recientes | `text`, `uniqueId` del actor de comentarios | Calidad de comentarios |
| Bio y captions | `authorMeta.signature`, `text` | Lenguaje de riesgo |

### Facebook Marketplace

Actor: `deepmine/facebook-marketplace-scraper`, con "Add listing details" activo.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Desde cuándo está en Facebook | `sellerJoinTime` | Antigüedad; menos de 1 mes es bandera roja |
| Otros anuncios del vendedor: fecha y ciudad de cada uno | Perfil del vendedor (`/marketplace/profile/<id>`) | Historial (detecta cuentas robadas) y coherencia de ubicación |
| URLs de las fotos del anuncio | `listingPhotos` | Fotos copiadas de otros vendedores (hash perceptual) |
| Título y descripción | `marketplaceListingTitle`, `redactedDescription` | Completitud y lenguaje de riesgo |
| Calificación promedio, cantidad e insignias | `sellerRatingAverage`, `sellerRatingCount`, `commerce_badges_info` | Bonus de hasta +10; menos de 3★ con 5+ calificaciones es bandera roja |

### Mercado Libre

API oficial: `/items/{id}`, `/items/{id}/description` y `/users/{id}`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Termómetro y MercadoLíder | `seller_reputation.level_id`, `power_seller_status` | Reputación; rojo con 10+ ventas es bandera roja |
| Ventas concretadas y totales | `seller_reputation.transactions.completed`, `total` | Volumen de ventas |
| Proporción de calificaciones negativas | `seller_reputation.transactions.ratings.negative` | Calificaciones negativas; 25 % o más es bandera roja |
| Fecha de registro | `registration_date` (confirmar que viene para terceros) | Antigüedad |
| Estado del vendedor y de la publicación | `address.state`, `seller_address.state.name` | Ubicación coherente |
| Estado de la cuenta | `status.site_status` | Cuenta suspendida es bandera roja |
| Fotos, descripción y garantía de la publicación | `pictures`, `plain_text`, `warranty` | Completitud, garantía y lenguaje de riesgo |

### Tiendas web

Firecrawl, RDAP, DNS y Google Safe Browsing.

| Dato | De dónde sale | Señal que alimenta |
|---|---|---|
| Fecha de registro del dominio | RDAP (`rdap.org/domain/<dominio>`) | Antigüedad; menos de 1 mes es bandera roja |
| RIF, dirección, teléfonos y correos | Extracción con schema de Firecrawl en portada, contacto y nosotros | Contacto verificable |
| Palabras de las páginas de términos, devoluciones, garantía y privacidad | Scrape de cada página | Políticas |
| Productos visibles | Extracción con schema | Catálogo |
| Redes enlazadas | Links del sitio | Enlaza redes |
| HTTPS, correo del dominio (MX) y si Google lo marca como peligroso | URL final, DNS, Safe Browsing | Técnico; marcado por Google es bandera roja |
| Texto de la portada | Markdown de Firecrawl | Lenguaje de riesgo |
| Si dice ser tienda oficial de una marca | Extracción con schema | Bandera roja si no está en el dominio de la marca |

### Amazon

Actores: `junglee/Amazon-crawler` y `reefapi/amazon-seller-scraper`.

| Dato | Campo de origen | Señal que alimenta |
|---|---|---|
| Quién vende y quién envía | `seller.name`, `shipsFrom` | Amazon, FBA o el vendedor. Si vende y envía Amazon, el puntaje es 95 directo |
| ID del vendedor | `seller.id` | Para pedir su perfil |
| Feedback positivo y calificaciones (de por vida y 12 meses) | `feedback_percent`, `lifetime_ratings`, `ratings_12m` | Feedback, volumen y actividad reciente (detecta cuentas robadas) |
| Texto y nota de reseñas de feedback recientes | `seller/reviews` | Reseñas de falsificación o envíos no recibidos |
| Nota y reseñas del producto | `stars`, `reviewsCount` | Historial del producto |

### Para todas las fuentes

- **Precio**: no lo trae la fuente. Lo calcula `search_offers` contra la mediana de las demás ofertas del mismo producto, con al menos 5 comparables.
- **Reportes de usuarios**: todavía no hay forma de reportar, así que no cuentan.
- **Meta Ads**: para ajustar el puntaje de Instagram, Marketplace o TikTok hace falta el ID de la página de Facebook vinculada. Si el actor de tu fuente lo trae, guárdalo.

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. El puntaje de tiendas web puede usar además `GOOGLE_SAFE_BROWSING_KEY`, que es opcional, y el de Mercado Libre, `ML_ACCESS_TOKEN`, el token de la app. Amazon usa `APIFY_TOKEN`. Agrégalas a `apps/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
