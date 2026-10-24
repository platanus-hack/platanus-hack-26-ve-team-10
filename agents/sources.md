# Fuentes e ingesta: packages/core/sources y apps/ingest

Las fuentes son de donde salen los precios y los datos de los comercios. Las de redes sociales tardan de segundos a minutos en responder, así que hay dos caminos:

- **Ingesta (por lotes):** `apps/ingest` recorre las fuentes con Cloud Scheduler y llena el índice. Es el camino principal.
- **En vivo:** el agente consulta una fuente rápida cuando el índice no tiene nada reciente. Solo para fuentes que respondan en pocos segundos.

## Fuentes

| Fuente | Qué trae | Cómo se consulta | Camino |
|---|---|---|---|
| **Firecrawl** | Webs de tiendas y catálogos | Paquete `firecrawl`: `scrape`, `crawl`, `search` y extracción con schema | Ingesta y en vivo |
| **Apify: Instagram** | Perfiles, publicaciones, comentarios y seguidores de tiendas | `apify-client` + actor `apify/instagram-scraper` | Ingesta |
| **Apify: TikTok** | Perfiles y publicaciones de tiendas | `apify-client` + actor `clockworks/tiktok-scraper` | Ingesta |
| **Apify: Facebook Marketplace** | Publicaciones de Marketplace | `apify-client` + un actor de Marketplace de la Apify Store. Facebook no tiene API oficial | Ingesta |
| **Mercado Libre** | Publicaciones de Mercado Libre Venezuela (sitio `MLV`) | API oficial. Responde **403 sin token**: hay que registrar una app y usar OAuth. Plan B: un actor de Apify | Ingesta y en vivo |
| **Meta Ads** | Comercios que anuncian productos | Ojo: la API de la Ad Library solo devuelve anuncios comerciales que se mostraron en la UE o el Reino Unido. Fuera de eso, solo anuncios políticos. Para Venezuela probablemente no sirve: hay que probar un actor de Apify sobre la Ad Library web | Ingesta |

Lo que no está confirmado: el actor de Facebook Marketplace (hay que elegirlo en la Apify Store) y el de Meta Ads. Prueba cada uno con datos reales antes de construir encima.

## Adapter

Cada fuente es un archivo en `packages/core/src/sources/`:

```ts
interface SourceAdapter {
  id: string;                  // "firecrawl", "apify-instagram", "mercadolibre"...
  name: string;
  mode: "ingest" | "live" | "both";
  search(query: string, signal: AbortSignal): Promise<Offer[]>;  // live
  collect?(target: IngestTarget): Promise<IngestBatch>;         // ingesta: ofertas y datos del comercio
}
```

## Reglas

- **Siempre guarda la evidencia.** Guarda la respuesta cruda en Cloud Storage y su ruta en la oferta. Si alguien duda de un precio, se puede mostrar de dónde salió.
- **Sin precio no hay inventos.** Si la publicación dice "precio al DM" o no tiene precio, la oferta va con `price: null` y puede abrir un caso en el human loop.
- **Una fuente que falla no frena la búsqueda.** Cada fuente tiene un timeout propio, y si falla va a `failedSources`.
- **Normaliza con core.** Monedas, títulos y zonas se normalizan en `packages/core`, nunca dentro del adapter.
- **Datos de confianza.** De Instagram y TikTok salen los seguidores y comentarios que usa el puntaje de confianza. Guárdalos con su fecha.
- **Costos.** Apify y Firecrawl cobran por uso. Cada job tiene un tope de resultados, y no se corre un actor por cada consulta de usuario.
- **Términos de uso.** Usa solo datos públicos y guarda los mínimos datos personales. Si una fuente tiene API oficial, se prefiere.
- **Tests sin red.** Cada adapter tiene un test con una respuesta guardada de la fuente.

## Variables

`FIRECRAWL_API_KEY`, `APIFY_TOKEN`, `MERCADOLIBRE_CLIENT_ID`, `MERCADOLIBRE_CLIENT_SECRET`. En GCP van en Secret Manager.

## Docs

- [Firecrawl: SDK de Node](https://docs.firecrawl.dev/sdk/node)
- [Apify: cliente de JavaScript](https://docs.apify.com/api/client/js/)
- [Mercado Libre Developers](https://developers.mercadolibre.com.ve)
- [Meta Ad Library API](https://www.facebook.com/ads/library/api/)
