# Fuentes

Cada fuente es un archivo en `apps/api/app/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). Hoy solo existe la de ejemplo (`mock.py`), que se apaga con `USE_MOCK_SOURCE=false`.

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | SDK de Python de Firecrawl: `search`, `scrape` y extracción con schema (confirma el paquete en su `llms.txt`) | Cobra por uso |
| **Apify: Instagram** | Cliente de Python de Apify + actor `apify/instagram-scraper` | Tarda de segundos a minutos. Muchas tiendas ponen "precio al DM": la oferta va con `price=None` |
| **Apify: TikTok** | Cliente de Python de Apify + actor `clockworks/tiktok-scraper` | Igual que Instagram |
| **Apify: Facebook Marketplace** | Cliente de Python de Apify + un actor de Marketplace de la Apify Store | Facebook no tiene API oficial. El actor está sin elegir |
| **Mercado Libre** | API oficial, sitio `MLV` | Responde **403 sin token**: hay que registrar una app. Plan B: un actor de Apify |
| **Meta Ads** | API de la Ad Library | Solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Para Venezuela probablemente no sirve: probar un actor de Apify |

## Reglas

- **Lento no va en vivo.** Cada fuente tiene 8 segundos (`asyncio.wait_for` la cancela). Si tarda más (Apify), el actor corre antes y el adapter lee su último resultado.
- **Sin precio no hay inventos.** Si la publicación no tiene precio, `price` va en `None`.
- **Una fuente que falla no tumba la búsqueda.** `search_offers` ya la deja fuera y la anota en `failedSources`.
- **Async de verdad.** `search` es `async`: usa clientes asíncronos (`httpx.AsyncClient`) para no bloquear a las demás fuentes.
- **Guarda los datos del comercio** (seguidores, comentarios), porque los usa el puntaje de confianza.

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. Agrégalas a `apps/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
