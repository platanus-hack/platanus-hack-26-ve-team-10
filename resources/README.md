# Resources

Material de referencia. Aquí no hay instrucciones: las instrucciones están en [agents/](../agents/).

Qué va aquí:

- `sources.md`: comercios y canales candidatos (nombre, URL, fuente, si publica precios).
- `keywords-ve.csv` / `keywords-ve.md`: búsquedas de Google en Venezuela con volumen e intención, y hallazgos para taxonomía y URLs.
- `usaprais.com-agentic-architecture.pdf`: diagrama de la pizarra (fuentes, agentes y canales). El sistema que está construido es el de [agents/architecture.md](../agents/architecture.md).
- `queries.md`: consultas de ejemplo para probar el agente, con la respuesta que esperamos.
- `ig-trust-score.ts`: borrador en TypeScript del puntaje de confianza de una cuenta de Instagram con Apify: 11 señales con peso, banderas rojas, cobertura mínima y veredicto. Es referencia para el puntaje de confianza, que va en Python en `apps/api/app/lib/prices.py`. No se ejecuta ni se importa.
- Investigación, capturas y datos de ejemplo de cada fuente.
