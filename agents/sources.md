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
- **Guarda los datos del comercio** (seguidores, comentarios, reputación), porque los usa el puntaje de confianza: ver [Puntaje de confianza por fuente](#puntaje-de-confianza-por-fuente).

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

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. El puntaje de tiendas web puede usar además `GOOGLE_SAFE_BROWSING_KEY`, que es opcional, y el de Mercado Libre, `ML_ACCESS_TOKEN`, el token de la app. Amazon usa `APIFY_TOKEN`. Agrégalas a `apps/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
