# Fuentes

Cada fuente es un archivo en `apps/api/app/lib/sources/` que cumple el contrato `Source`. Los pasos para sumar una están en [contracts.md](contracts.md#sumar-una-fuente). Hoy solo existe la de ejemplo (`mock.py`), que se apaga con `USE_MOCK_SOURCE=false`. Además de sus ofertas fijas, la de ejemplo responde por cada modelo del catálogo (`catalogo.json`) con comercios marcados "(ejemplo)" y precios generados desde `precioEjemplo`. Apagarla deja el catálogo con solo ofertas reales: ver [seo-geo.md](seo-geo.md#catálogo-el-interruptor-de-indexación).

## Qué hay que saber de cada una

| Fuente | Cómo se consulta | Ojo |
|---|---|---|
| **Firecrawl** | El especialista `open_web` busca `{producto} precio Venezuela` (`location` Caracas, `country` VE, 5 resultados) y lee el precio con extracción JSON de hasta 3 páginas (`app/lib/sources/firecrawl.py`). No entra en `search_offers`: pasa de 8 s y cobra por uso | Cobra por uso. El puntaje de confianza de tiendas web todavía no se calcula (borrador en [resources/website-trust-score.ts](../resources/website-trust-score.ts)) |
| **Apify: Instagram** | Cliente de Python de Apify + actor `apify/instagram-scraper` | Tarda de segundos a minutos. Muchas tiendas ponen "precio al DM": la oferta va con `price=None` |
| **Apify: TikTok** | Cliente de Python de Apify + actor `clockworks/tiktok-scraper` | Igual que Instagram. El puntaje de confianza usa `clockworks/tiktok-profile-scraper` y `clockworks/tiktok-comments-scraper` (ver [resources/tiktok-trust-score.ts](../resources/tiktok-trust-score.ts)) |
| **Apify: Facebook Marketplace** | Cliente de Python de Apify + un actor de Marketplace de la Apify Store | Facebook no tiene API oficial. Candidato: `deepmine/facebook-marketplace-scraper`, con proxy residencial (ver [resources/fb-marketplace-trust-score.ts](../resources/fb-marketplace-trust-score.ts)) |
| **Mercado Libre** | API oficial, sitio `MLV` | Responde **403 sin token**: hay que registrar una app. Plan B: un actor de Apify |
| **Meta Ads** | API de la Ad Library | Solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Para Venezuela no sirve. Candidato: el actor `curious_coder/facebook-ads-library-scraper`, que se usa para ajustar el puntaje de confianza (ver [resources/meta-ads-signals.ts](../resources/meta-ads-signals.ts)) |

## Reglas

- **Lento no va en vivo.** Cada fuente tiene 8 segundos (`asyncio.wait_for` la cancela). Si tarda más (Apify), el actor corre antes y el adapter lee su último resultado.
- **Sin precio no hay inventos.** Si la publicación no tiene precio, `price` va en `None`.
- **Una fuente que falla no tumba la búsqueda.** `search_offers` ya la deja fuera y la anota en `failedSources`.
- **Async de verdad.** `search` es `async`: usa clientes asíncronos (`httpx.AsyncClient`) para no bloquear a las demás fuentes.
- **Guarda los datos del comercio** (seguidores, comentarios), porque los usa el puntaje de confianza. Para Instagram, las señales, los pesos y los actores de Apify (`instagram-profile-scraper` e `instagram-comment-scraper`) están en [resources/ig-trust-score.ts](../resources/ig-trust-score.ts). Para Facebook Marketplace, en [resources/fb-marketplace-trust-score.ts](../resources/fb-marketplace-trust-score.ts): ahí la reputación sale del historial del vendedor y de las fotos repetidas, porque en Venezuela casi nadie califica. Para TikTok, en [resources/tiktok-trust-score.ts](../resources/tiktok-trust-score.ts): ahí se mide la proporción entre likes y vistas, no los likes por seguidor, porque las vistas las reparte el algoritmo. Encima de cualquiera de los tres se aplican los ajustes de Meta Ads de [resources/meta-ads-signals.ts](../resources/meta-ads-signals.ts): un vendedor que no anuncia no pierde nada. Para tiendas web, en [resources/website-trust-score.ts](../resources/website-trust-score.ts): pesan la antigüedad del dominio, el RIF y los datos de contacto publicados y las políticas de devolución. Todos son borradores en TypeScript: pórtalos a Python en `prices.py` y confirma los campos de cada actor antes de usarlos.

## Variables

`FIRECRAWL_API_KEY` y `APIFY_TOKEN`. El puntaje de tiendas web puede usar además `GOOGLE_SAFE_BROWSING_KEY`, que es opcional. Agrégalas a `apps/api/.env.example` cuando conectes la fuente. En producción ya tienen lugar en el secreto `prais-api-secrets` ([gcp.md](gcp.md)).

## Docs

- Firecrawl: [llms.txt](https://docs.firecrawl.dev/llms.txt), para el SDK de Python
- Apify: [llms.txt](https://docs.apify.com/llms.txt), para el cliente de Python
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
