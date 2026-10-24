# Fuentes

Cada fuente es un archivo en `apps/api/src/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). Hoy solo existe la de ejemplo (`mock.ts`), que se apaga con `USE_MOCK_SOURCE=false`.

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | Paquete `firecrawl`: `search`, `scrape` y extracción con schema | Cobra por uso |
| **Apify: Instagram** | `apify-client` + actor `apify/instagram-scraper` | Tarda de segundos a minutos. Muchas tiendas ponen "precio al DM": la oferta va con `price: null` |
| **Apify: TikTok** | `apify-client` + actor `clockworks/tiktok-scraper` | Igual que Instagram |
| **Apify: Facebook Marketplace** | `apify-client` + un actor de Marketplace de la Apify Store | Facebook no tiene API oficial. El actor está sin elegir |
| **Mercado Libre** | API oficial, sitio `MLV` | Responde **403 sin token**: hay que registrar una app. Plan B: un actor de Apify |
| **Meta Ads** | API de la Ad Library | Solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Para Venezuela probablemente no sirve: probar un actor de Apify |

## Reglas

- **Lento no va en vivo.** Cada fuente tiene 8 segundos. Si tarda más (Apify), el actor corre antes y el adapter lee su último resultado.
- **Sin precio no hay inventos.** Si la publicación no tiene precio, `price` va en `null`.
- **Una fuente que falla no tumba la búsqueda.** `searchOffers` ya la deja fuera y la anota en `failedSources`.
- **Guarda los datos del comercio** (seguidores, comentarios), porque los usa el puntaje de confianza.

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. Agrégalas a `apps/api/.env.example` cuando conectes la fuente.

## Docs

- [Firecrawl: SDK de Node](https://docs.firecrawl.dev/sdk/node)
- [Apify: cliente de JavaScript](https://docs.apify.com/api/client/js/)
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
