# Resources

Material de referencia. Aquí no hay instrucciones: las instrucciones están en [agents/](../agents/).

Qué va aquí:

- `sources.md`: comercios y canales candidatos (nombre, URL, fuente, si publica precios).
- `keywords-ve.csv` / `keywords-ve.md`: búsquedas de Google en Venezuela con volumen e intención, y hallazgos para taxonomía y URLs.
- `usaprais.com-agentic-architecture.pdf`: diagrama de la pizarra (fuentes, agentes y canales). El sistema que está construido es el de [agents/architecture.md](../agents/architecture.md).
- `queries.md`: consultas de ejemplo para probar el agente, con la respuesta que esperamos.
- `ig-trust-score.ts`: borrador en TypeScript del puntaje de confianza de una cuenta de Instagram con Apify: 11 señales con peso, banderas rojas, cobertura mínima y veredicto. Es referencia para el puntaje de confianza, que va en Python en `apps/api/app/lib/prices.py`. No se ejecuta ni se importa.
- `fb-marketplace-trust-score.ts`: lo mismo para un anuncio y su vendedor en Facebook Marketplace: 8 señales con peso (antigüedad en Facebook, ubicación, historial de publicaciones, fotos originales, completitud, lenguaje de riesgo, precio y reportes), un bonus de hasta +10 por calificaciones e insignias, y banderas rojas. Tampoco se ejecuta.
- `tiktok-trust-score.ts`: lo mismo para una cuenta de TikTok: 11 señales con peso. Mide la proporción entre likes, vistas, compartidos y guardados en lugar de likes por seguidor, y saca la antigüedad de la cuenta del ID de usuario. Tampoco se ejecuta.
- Investigación, capturas y datos de ejemplo de cada fuente.
