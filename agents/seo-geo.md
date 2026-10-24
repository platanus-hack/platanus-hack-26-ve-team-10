# SEO y GEO

SEO es aparecer en buscadores. GEO es aparecer citado en las respuestas de los asistentes de IA, como ChatGPT, Gemini, Perplexity o Claude. Las dos cosas premian lo mismo: páginas rápidas, contenido claro y datos verificables. Prais tiene una ventaja: publica precios con fuente y fecha, que es justo lo que se puede citar.

## Qué páginas compiten

Hoy existen `/`, `/privacidad` y `/terminos`. Las demás de la tabla son para cuando la demo las necesite.

| Página | Indexable | Para qué |
|---|---|---|
| Landing `/` | Sí | Marca, propuesta y el chat |
| Privacidad `/privacidad` y términos `/terminos` | Sí | Los pide Meta para verificar el negocio y el número de WhatsApp. Los datos legales y de contacto están en `apps/web/src/lib/empresa.ts` y tienen que coincidir con los documentos de la empresa |
| Blog `/blog/...` | Sí | Preguntas que la gente busca: "dónde comprar X más barato en Caracas" |
| Producto `/ve/p/[slug]-[id]` | Sí | La comparación de precios de un producto. Es la página que más tráfico puede traer. Detalle en [docs/ficha-producto.md](../docs/ficha-producto.md) |
| Categoría `/ve/[categoria]/`, `/ve/[categoria]/[marca]/` | Sí, con reglas | Listado de modelos por categoría, marca o faceta con demanda. Detalle en [docs/categoria.md](../docs/categoria.md) |
| Marca `/ve/marca/[slug]/` y `/ve/marcas/` | Sí, si vende en 2+ categorías | Hub de la marca hacia sus categorías. Detalle en [docs/marca.md](../docs/marca.md) |
| Comercio `/ve/comercios/[slug]` | Pospuesta | Perfil del comercio con su puntaje de confianza. Por ahora no se hace |
| Dashboard y admin | No | Están bloqueados en `robots.ts` |

## Cada página pública

- `generateMetadata` con title, description, `canonical` y Open Graph.
- `<html lang="es-VE">`.
- JSON-LD de schema.org:
  - Landing: `Organization` y `WebSite`. Falta el `SearchAction`: la landing todavía no recibe la búsqueda por URL.
  - Blog: `BlogPosting`.
  - Producto: `Product` con `AggregateOffer` (`lowPrice`, `highPrice`, `priceCurrency`, `offerCount`).
  - Comercio: `LocalBusiness` u `Organization`, según tenga local físico o no.
  - Preguntas frecuentes: `FAQPage`.
- Las páginas de producto, categoría y marca se generan estáticas o con revalidación, nunca solo en el cliente: un crawler tiene que ver los precios en el HTML.

## Para GEO

- Responde primero. El primer párrafo contesta la pregunta, y después viene el detalle.
- Cada precio va con su fuente y su fecha ("visto el 24 de octubre en ..."). Los asistentes citan lo que pueden verificar.
- Publica `/llms.txt` con qué es Prais y enlaces a las páginas clave.
- `robots.ts` deja pasar a los crawlers de IA (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`), porque queremos que nos citen.
- **Si activan el proxy de Cloudflare**, revisa su configuración de bots. Cloudflare bloquea por defecto los crawlers de IA en los dominios nuevos. Apaga el bloqueo de bots de IA y el `robots.txt` administrado, o el `robots.ts` no va a servir de nada. Con los registros en "DNS only" esto no aplica.

## Archivos

- `app/sitemap.ts`: landing, posts del blog y las páginas de producto, categoría y marca que estén abiertas para indexar.
- `app/robots.ts`: reglas de arriba, más la URL del sitemap.
- `public/llms.txt`: o una ruta, si se genera desde los datos.
