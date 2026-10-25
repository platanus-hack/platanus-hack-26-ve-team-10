# SEO y GEO

SEO es aparecer en buscadores. GEO es aparecer citado en las respuestas de los asistentes de IA, como ChatGPT, Gemini, Perplexity o Claude. Las dos cosas premian lo mismo: páginas rápidas, contenido claro y datos verificables. Prais tiene una ventaja: publica precios con fuente y fecha, que es justo lo que se puede citar.

## Qué páginas compiten

Hoy existen `/`, las guías, `/privacidad`, `/terminos` y el catálogo de Venezuela (`/ve/...`: producto, categoría, categoría + marca, faceta, marca e índice de marcas). El blog y el comercio quedan para después.

| Página | Indexable | Para qué |
|---|---|---|
| Landing `/` | Sí | Marca, propuesta y el chat |
| Guías `/comparador-de-precios`, `/comparador-de-celulares`, `/que-es-usaprais` | Sí | Responder búsquedas del concepto ("comparar celulares" 1.000/mes, "comparador de teléfonos" 590) y que los asistentes de IA encuentren qué es usaprais, también como usaprice o usaprices. El contenido vive en `services/web/src/lib/guias.ts`; para agregar una guía, súmala ahí y crea su carpeta con el `page.tsx` de 5 líneas |
| Privacidad `/privacidad` y términos `/terminos` | Sí | Los pide Meta para verificar el negocio y el número de WhatsApp. Los datos legales y de contacto están en `services/web/src/lib/empresa.ts` y tienen que coincidir con los documentos de la empresa |
| Blog `/blog/...` | Sí | Preguntas que la gente busca: "dónde comprar X más barato en Caracas" |
| Producto `/ve/p/[slug]-[id]` | Sí, con ofertas reales | La comparación de precios de un producto. Es la página que más tráfico puede traer. Detalle en [docs/ficha-producto.md](../docs/ficha-producto.md) |
| Categoría `/ve/[categoria]`, `/ve/[categoria]/[marca o faceta]` | Sí, con reglas | Listado de modelos por categoría, marca o faceta con demanda. Detalle en [docs/categoria.md](../docs/categoria.md) |
| Marca `/ve/marca/[slug]/` y `/ve/marcas/` | Sí, si vende en 2+ categorías | Hub de la marca hacia sus categorías. Detalle en [docs/marca.md](../docs/marca.md) |
| Comercio `/ve/comercios/[slug]` | Pospuesta | Perfil del comercio con su puntaje de confianza. Por ahora no se hace |
| Dashboard y admin | No | Están bloqueados en `robots.ts` |

## Cada página pública

- `generateMetadata` con title, description, `canonical` y Open Graph.
- `<html lang="es-VE">`.
- JSON-LD de schema.org:
  - Landing: `Organization` y `WebSite`. Falta el `SearchAction`: la landing todavía no recibe la búsqueda por URL.
  - Blog: `BlogPosting`.
  - Producto: `Product` con `AggregateOffer` (`lowPrice`, `highPrice`, `priceCurrency`, `offerCount`), solo cuando la página es indexable: nunca con precios de ejemplo.
  - Categoría: `ItemList` con las fichas listadas. Todas las páginas del catálogo: `BreadcrumbList`.
  - Comercio: `LocalBusiness` u `Organization`, según tenga local físico o no.
  - Preguntas frecuentes: `FAQPage`.
- Las páginas de producto, categoría y marca se generan estáticas o con revalidación, nunca solo en el cliente: un crawler tiene que ver los precios en el HTML.

## Catálogo: el interruptor de indexación

El catálogo (categorías, marcas, modelos y facetas) está en `services/api/app/lib/catalogo.json`, generado desde la investigación de keywords (`resources/keywords-ve.csv`) con `services/api/scripts/catalogo_semilla.py`. Los precios **no** están ahí: `services/api/app/lib/catalogo.py` se los pide a `search_offers` por cada modelo, igual que el agente.

- Cada página que devuelve la API trae `indexable` y `datosDeEjemplo`. Una página es indexable solo con ofertas de fuentes reales (cualquier fuente que no sea `ejemplo`), con los umbrales de los docs: ficha con 1 oferta real, categoría + marca y faceta con 5 modelos reales, marca con 2 categorías reales.
- Con datos de ejemplo la página sale con `noindex, follow`, fuera del sitemap, sin `Product` en el schema y con el aviso "Datos de demostración". Google nunca ve precios inventados como si fueran reales.
- **Pasar a datos reales no toca la web ni el catálogo:** se conecta una fuente en `services/api/app/lib/sources/` y se apaga la de ejemplo con `USE_MOCK_SOURCE=false`. Las páginas con ofertas reales se vuelven indexables y entran al sitemap solas, en la siguiente revalidación (1 h).
- Para sumar modelos, categorías o facetas, edita `catalogo_semilla.py` y vuelve a generar `catalogo.json`. Cuando el scraping traiga el catálogo real, reemplaza ese JSON.

Pendiente del catálogo v1 respecto a los docs: paginación (hoy ninguna categoría pasa de 32 modelos), historial de precios, métodos de pago (no hay datos), filtros de precio y pago, y la regla anti-parpadeo (hoy una página se abre o se cierra en la siguiente revalidación).

## Para GEO

- Responde primero. El primer párrafo contesta la pregunta, y después viene el detalle.
- Cada precio va con su fuente y su fecha ("visto el 24 de octubre en ..."). Los asistentes citan lo que pueden verificar.
- Publica `/llms.txt` con qué es Prais y enlaces a las páginas clave.
- `robots.ts` deja pasar a los crawlers de IA (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`), porque queremos que nos citen.
- **Si activan el proxy de Cloudflare**, revisa su configuración de bots. Cloudflare bloquea por defecto los crawlers de IA en los dominios nuevos. Apaga el bloqueo de bots de IA y el `robots.txt` administrado, o el `robots.ts` no va a servir de nada. Con los registros en "DNS only" esto no aplica.

## Archivos

- `app/sitemap.ts`: landing, guías, `/ve/marcas`, privacidad y términos, más las páginas del catálogo indexables (`GET /catalogo/sitemap` de la API). Las guías salen de `lib/guias.ts`.
- `app/ve/`: las páginas del catálogo, con `ensureStatic = "navigation"`: se generan estáticas al construir (`generateStaticParams` con `GET /catalogo/rutas`) y se revalidan cada hora. Los datos salen de `lib/catalogo.ts`, que solo le pregunta a la API. Si la API no responde al construir, el build no se rompe: las páginas se generan al primer pedido.
- `app/robots.ts`: deja pasar a todos, nombra a los crawlers de IA y apunta al sitemap. `/api/` queda fuera.
- `app/llms.txt/route.ts` y `app/llms-full.txt/route.ts`: el índice y el contenido completo según [llmstxt.org](https://llmstxt.org), generados desde `lib/guias.ts` y `lib/empresa.ts`. Se prerenderizan en el build.
