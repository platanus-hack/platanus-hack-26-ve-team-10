# Arquitectura

Una sola app de Next.js en un solo servicio de Cloud Run. El agente, el webhook de WhatsApp y el servidor MCP son rutas de esa misma app.

```
Web (chat) ──────────► /api/chat ──────┐
WhatsApp ─► Kapso ───► /api/whatsapp ──┼─► agente (ADK) ─► searchOffers ─► fuentes
                                       │                    (src/lib)      hoy: datos de ejemplo
ChatGPT / Claude ────► /api/mcp ───────┴──────────────────► searchOffers
```

- **El agente** (`src/agent`) conversa: pregunta lo que falta (producto, zona, envío), busca con la tool `buscar_ofertas` y explica la mejor opción.
- **`searchOffers`** (`src/lib/search.ts`) es el único punto que toca las fuentes. Devuelve las ofertas ordenadas por precio en USD, con la tasa usada y la confianza de cada comercio. Hoy lee datos de ejemplo. Conectar una fuente real es cambiar esta función: ver [sources.md](sources.md).
- **MCP** llama directo a `searchOffers`, sin el agente, porque quien pregunta ya es un asistente de IA.

## Qué hay y qué falta

| Pieza | Estado |
|---|---|
| Página con chat | Hecha |
| Agente con una tool | Hecho. Falta probarlo con una API key |
| Webhook de WhatsApp | Hecho. Falta configurarlo en Kapso |
| MCP con `search_prices` | Hecho |
| Confianza del comercio | Fórmula inicial en `src/lib/prices.ts` |
| Fuentes reales | Faltan: Firecrawl, Apify, Mercado Libre, Meta Ads |
| Deploy en Cloud Run | Pendiente: lo arma el dev a cargo de GCP. Requisitos en [gcp.md](gcp.md) |
| Directorio de comercios, admin, human loop | Cuando la demo los necesite |

## Decisiones tomadas (2026-10-24)

- Una app de Next.js con TypeScript y pnpm, desplegada en Cloud Run (GCP). Cloudflare solo maneja el DNS.
- El deploy lo hace Cloud Build, y solo construye si cambió la app. No usamos GitHub Actions para desplegar ni el mirror `Pleo2/prais.com`.
- Agente con ADK para TypeScript y Gemini.
- WhatsApp con Kapso, y MCP como ruta de la app.
- Un solo agente con tools. Los sub-agentes de la pizarra se agregan si un solo agente no alcanza.
- Las sesiones del agente viven en memoria. Si se pierden con un reinicio, no importa para la demo.

## Decisiones abiertas

1. Qué fuentes se conectan primero.
2. Qué tasa de referencia se usa (BCV, paralela o ambas) y de dónde sale.
3. Si hace falta base de datos. Por ahora no: los datos de ejemplo están en código.
