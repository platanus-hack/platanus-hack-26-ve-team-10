# Arquitectura

Dos apps en un monorepo de pnpm: un backend en Fastify que hace todo el trabajo y una web en Next.js que solo muestra.

```
Web (Next.js) ── /api/* ──┐
                          ▼
WhatsApp ─► Kapso ─► apps/api (Fastify)
                      ├─ POST /chat      ─► agente ADK ─┐
                      ├─ POST /whatsapp  ─► agente ADK ─┼─► searchOffers ─► fuentes
                      └─ /mcp            ───────────────┘   (src/lib)      hoy: datos de ejemplo
ChatGPT / Claude ─────┘
```

- **`apps/api`**: Fastify con tres rutas y `/health`. Cada ruta es un plugin en `src/routes/`, registrado en `src/server.ts`.
- **El agente** (`src/agent.ts`) conversa: pregunta lo que falta (producto, zona, envío), busca con la tool `buscar_ofertas` y explica la mejor opción.
- **`searchOffers`** (`src/lib/search.ts`) llama en paralelo a todas las fuentes de `src/lib/sources/`, convierte, filtra y ordena. Los contratos entre las piezas están en [contracts.md](contracts.md).
- **MCP** llama directo a `searchOffers`, sin el agente, porque quien pregunta ya es un asistente de IA.
- **`apps/web`** reenvía `/api/*` al backend con un rewrite de Next. Así el navegador habla con un solo dominio y no hace falta CORS. Ojo: `API_URL` se lee al **construir** la web, no al arrancarla.

## Qué hay y qué falta

| Pieza | Estado |
|---|---|
| Web con chat | Hecha |
| Agente con una tool | Hecho. Falta probarlo con una API key |
| Webhook de WhatsApp | Hecho. Falta configurarlo en Kapso |
| MCP con `search_prices` | Hecho |
| Confianza del comercio | Fórmula inicial en `apps/api/src/lib/prices.ts` |
| Fuentes reales | Faltan: Firecrawl, Apify, Mercado Libre, Meta Ads |
| Deploy en GCP | Pendiente: lo arma el dev a cargo. Requisitos en [gcp.md](gcp.md) |

## Decisiones tomadas (2026-10-24)

- Backend en Fastify con el agente (ADK para TypeScript y Gemini), Kapso y MCP. Web en Next.js, solo interfaz.
- Infraestructura en GCP, con Cloud Build para desplegar. Cloudflare solo maneja el DNS.
- Un solo agente con tools. Los sub-agentes de la pizarra se agregan si un solo agente no alcanza.
- Las sesiones del agente viven en memoria. Si se pierden con un reinicio, no importa para la demo.

## Decisiones abiertas

1. Qué fuentes se conectan primero.
2. Qué tasa de referencia se usa (BCV, paralela o ambas) y de dónde sale.
3. Si hace falta base de datos. Por ahora no: los datos de ejemplo están en código.
