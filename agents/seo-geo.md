# SEO y GEO

SEO es aparecer en buscadores. GEO es aparecer citado en las respuestas de los asistentes de IA, como ChatGPT, Gemini, Perplexity o Claude. Las dos cosas premian lo mismo: páginas rápidas, contenido claro y datos verificables. Prais tiene una ventaja: publica precios con fuente y fecha, que es justo lo que se puede citar.

## Qué páginas compiten

Hoy solo existe `/`. Las demás de la tabla son para cuando la demo las necesite.

| Página | Indexable | Para qué |
|---|---|---|
| Landing `/` | Sí | Marca, propuesta y el chat |
| Blog `/blog/...` | Sí | Preguntas que la gente busca: "dónde comprar X más barato en Caracas" |
| Producto `/ve/p/[slug]-[id]` | Sí | La comparación de precios de un producto. Es la página que más tráfico puede traer. Detalle en [docs/ficha-producto.md](../docs/ficha-producto.md) |
| Comercio `/comercios/[slug]` | Sí | Perfil del comercio con su puntaje de confianza |
| Dashboard y admin | No | Están bloqueados en `robots.ts` |

## Cada página pública

- `generateMetadata` con title, description, `canonical` y Open Graph.
- `<html lang="es-VE">`.
- JSON-LD de schema.org:
  - Landing: `Organization` y `WebSite` con `SearchAction`.
  - Blog: `BlogPosting`.
  - Producto: `Product` con `AggregateOffer` (`lowPrice`, `highPrice`, `priceCurrency`, `offerCount`).
  - Comercio: `LocalBusiness` u `Organization`, según tenga local físico o no.
  - Preguntas frecuentes: `FAQPage`.
- Las páginas de producto y de comercio se generan estáticas o con revalidación, nunca solo en el cliente: un crawler tiene que ver los precios en el HTML.

## Para GEO

- Responde primero. El primer párrafo contesta la pregunta, y después viene el detalle.
- Cada precio va con su fuente y su fecha ("visto el 24 de octubre en ..."). Los asistentes citan lo que pueden verificar.
- Publica `/llms.txt` con qué es Prais y enlaces a las páginas clave.
- `robots.ts` deja pasar a los crawlers de IA (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`), porque queremos que nos citen.
- **Si activan el proxy de Cloudflare**, revisa su configuración de bots. Cloudflare bloquea por defecto los crawlers de IA en los dominios nuevos. Apaga el bloqueo de bots de IA y el `robots.txt` administrado, o el `robots.ts` no va a servir de nada. Con los registros en "DNS only" esto no aplica.

## Archivos

- `app/sitemap.ts`: landing, posts del blog y todas las páginas de producto y de comercio.
- `app/robots.ts`: reglas de arriba, más la URL del sitemap.
- `public/llms.txt`: o una ruta, si se genera desde los datos.
