# Resources

Material de referencia. Aquí no hay instrucciones: las instrucciones están en [agents/](../agents/).

Qué va aquí:

- `sources.md`: comercios y canales candidatos (nombre, URL, fuente, si publica precios).
- `keywords-ve.csv` / `keywords-ve.md`: búsquedas de Google en Venezuela con volumen e intención, y hallazgos para taxonomía y URLs.
- `usaprais.com-agentic-architecture.pdf`: diagrama de la pizarra (fuentes, agentes y canales). El sistema que está construido es el de [agents/architecture.md](../agents/architecture.md).
- `queries.md`: consultas de ejemplo para probar el agente, con la respuesta que esperamos.
- `*-trust-score.ts` y `meta-ads-signals.ts`: borradores del puntaje de confianza de cada fuente, en TypeScript. La implementación va en Python en `apps/api/app/lib/prices.py`: estos archivos no se importan. El resumen por fuente está en [agents/sources.md](../agents/sources.md#puntaje-de-confianza-por-fuente).
- `ig-trust-score.ts`: cuenta de Instagram con Apify: 11 señales con peso, banderas rojas, cobertura mínima y veredicto.
- `fb-marketplace-trust-score.ts`: un anuncio y su vendedor en Facebook Marketplace: 8 señales con peso (antigüedad en Facebook, ubicación, historial de publicaciones, fotos originales, completitud, lenguaje de riesgo, precio y reportes), un bonus de hasta +10 por calificaciones e insignias, y banderas rojas.
- `tiktok-trust-score.ts`: cuenta de TikTok: 11 señales con peso. Mide la proporción entre likes, vistas, compartidos y guardados en lugar de likes por seguidor, y saca la antigüedad de la cuenta del ID de usuario.
- `meta-ads-signals.ts`: capa que se suma a los tres puntajes anteriores, con datos de la Biblioteca de Anuncios de Meta vía Apify. No da un puntaje propio. Ajusta el de Instagram, Marketplace o TikTok con un bonus de hasta +5, una penalización de hasta −15 y banderas rojas: rotación rápida de anuncios, páginas renombradas con administradores fuera del país, dominios que imitan marcas y precios fuera de mercado. Incluye un radar diario de anuncios con precios sospechosos.
- `website-trust-score.ts`: tienda web con Firecrawl, RDAP (antigüedad del dominio), DNS (MX) y Google Safe Browsing. 11 señales con peso: RIF, dirección y teléfono publicados, políticas de devolución y garantía, catálogo, redes enlazadas (puede reusar sus puntajes de Instagram o TikTok), HTTPS, lenguaje de riesgo, precio y reportes. Marca como bandera roja los dominios que imitan una marca o que dicen ser tienda oficial sin serlo.
- `mercadolibre-trust-score.ts`: publicación y su vendedor en Mercado Libre Venezuela (`MLV`) con la API oficial. Aquí la reputación nativa sí es la señal principal: termómetro, MercadoLíder, ventas concretadas y calificaciones negativas. Suma antigüedad, ubicación, completitud, garantía, lenguaje de riesgo, precio y reportes.
- `amazon-trust-score.ts`: vendedor externo de Amazon para una oferta, con Apify. Pesan quién envía (Amazon, FBA o el vendedor), el feedback positivo y su volumen, la actividad reciente y las reseñas de falsificación o envíos no recibidos. Si vende y envía Amazon, el puntaje es 95 sin más cálculo.
- Investigación, capturas y datos de ejemplo de cada fuente.
