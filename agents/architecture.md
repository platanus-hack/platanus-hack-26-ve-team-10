# Arquitectura

Dos apps en un monorepo de pnpm: un backend en Python (FastAPI) que hace todo el trabajo y una web en Next.js que solo muestra.

```
Web (Next.js) ── /api/* ──┐
                          ▼
WhatsApp ─► Kapso ─► apps/api (FastAPI)
                      ├─ POST /chat      ─► agente ADK ─┐
                      ├─ POST /whatsapp  ─► Cloud Tasks ─► POST /internal/whatsapp-task ─► agente ADK ─┤
                      └─ /mcp            ──────────────────────────────────────────────────────────────┤
ChatGPT / Claude ─────┘                                                     search_offers ─► fuentes ◄──┘
                                                                            (app/lib)       hoy: datos de ejemplo
```

- **`apps/api`**: FastAPI con tres rutas, `/health` y una ruta interna para la cola. Cada ruta es un router en `app/routes/`, registrado en `app/main.py`.
- **El orquestador** (`app/agents/orchestrator.py`, corrido desde `app/agent.py`) entiende qué producto o servicio comparar, pide el hallazgo a un especialista por fuente y resume. Los especialistas no hablan con la persona.
- **`search_offers`** (`app/lib/search.py`) llama en paralelo a todas las fuentes de `app/lib/sources/`, convierte, filtra y ordena. Los contratos entre las piezas están en [contracts.md](contracts.md).
- **WhatsApp** pasa por una cola de Cloud Tasks (`app/lib/tasks.py`): el webhook valida la firma, encola un mensaje por tarea y responde 200; la cola llama a `/internal/whatsapp-task`, que corre el agente y responde por Kapso. Así hay reintentos y no se procesa dos veces el mismo mensaje. Detalle en [kapso.md](kapso.md).
- **MCP** llama directo a `search_offers`, sin el agente, porque quien pregunta ya es un asistente de IA.
- **El catálogo** (`app/lib/catalogo.py`, rutas `GET /catalogo/*` en `app/routes/catalogo.py`) arma las páginas públicas `/ve/...`: los modelos salen de `catalogo.json` y los precios, de `search_offers`.
- **`apps/web`** reenvía `/api/*` al backend con un rewrite de Next. Así el navegador habla con un solo dominio y no hace falta CORS. Ojo: `API_URL` se lee al **construir** la web, no al arrancarla.

## Qué hay y qué falta

| Pieza | Estado |
|---|---|
| Web con chat | Hecha |
| Orquestador y la web abierta | Hecho y probado por WhatsApp. Mercado Libre, Facebook, Instagram, TikTok y Meta Ads están apagados (`PAUSED_TOOLS`) hasta conectar cada fuente |
| Webhook de WhatsApp | Hecho. El número de producción apunta al API en Cloud Run. Probado en el sandbox de Kapso |
| MCP con `search_prices` | Hecho |
| Catálogo SEO (`/ve/...`) | Hecho con datos de ejemplo: 147 modelos, 28 categorías. Se indexa solo cuando hay ofertas reales: ver [seo-geo.md](seo-geo.md) |
| Confianza del comercio | Fórmula inicial en `apps/api/app/lib/prices.py`. Los borradores por fuente (Instagram, Marketplace, TikTok, tiendas web, Mercado Libre, Amazon y Meta Ads) están en `resources/`, resumidos en [sources.md](sources.md#puntaje-de-confianza-por-fuente) |
| Fuentes reales | Faltan: Firecrawl, Apify, Mercado Libre, Meta Ads |
| Deploy en GCP | Armado: `infra/` y `cloudbuild.*.yaml`. Cómo funciona, en [gcp.md](gcp.md) |

## Decisiones tomadas (2026-10-24)

- Agente con ADK y Gemini, Kapso y MCP en el backend. Web en Next.js, solo interfaz.
- Infraestructura en GCP, con Cloud Build para desplegar. Cloudflare solo maneja el DNS.
- Un orquestador (`root_agent`) y un especialista por fuente de la pizarra ([resources/usaprais.com-agentic-architecture.pdf](../resources/usaprais.com-agentic-architecture.pdf)). El orquestador resume. Los especialistas le reportan a él y no hablan con la persona.
- Las sesiones del agente viven en memoria. Si se pierden con un reinicio, no importa para la demo.

> **Backend: de Fastify a Python (FastAPI).** El backend se reescribió en Python conservando los contratos: las mismas rutas (`/chat`, `/whatsapp`, `/mcp`, `/health`), las mismas formas de entrada y salida y las mismas reglas. Lo único que cambia son los nombres internos, por el lenguaje (`searchOffers` → `search_offers`, `askPrais` → `ask_prais`, `getRate` → `get_rate`, tipos en `snake_case`) y que una fuente ya no recibe un `AbortSignal`: la búsqueda la cancela a los 8 s. Lo decidió quien arma el backend y la infra. El detalle está en [contracts.md](contracts.md).

## Decisiones abiertas

1. Qué fuentes se conectan primero.
2. Qué tasa de referencia se usa (BCV, paralela o ambas) y de dónde sale.
3. Si hace falta base de datos. Por ahora no: los datos de ejemplo están en código.
