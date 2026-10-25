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
                                                                            (app/lib)       registro: ejemplo,
                                                                                            Apify (IG, TikTok)
                                                                                            web abierta: Firecrawl
```

- **`apps/api`**: FastAPI. Los routers de `app/routes/` (`chat`, `whatsapp`, `catalogo`, `images`) y `/health` se registran en `app/main.py`. `/mcp` va montado al final. La ruta interna de la cola vive en el router de WhatsApp.
- **El orquestador** (`app/agents/orchestrator.py`, corrido desde `app/agent.py`) entiende qué producto o servicio comparar, llama una vez a cada fuente conectada (web abierta, Instagram y TikTok) y resume. Es el único que habla con la persona. Mercado Libre, Facebook Marketplace y Meta Ads siguen en `PAUSED_TOOLS`. Si el nombre todavía deja una elección que cambia el precio, `ask_prais` pregunta solo esa y no busca. El orden es el modelo (por ejemplo iPhone 14, Plus, Pro o Pro Max), después si lo quiere nuevo o usado, y después la capacidad. "Me da igual" cierra esa pregunta. Una respuesta escrita vale igual que tocar la opción. En WhatsApp las opciones van en una lista. El detalle está en [kapso.md](kapso.md).
- **`search_offers`** (`app/lib/search.py`) llama en paralelo a todas las fuentes de `app/lib/sources/`, convierte, filtra y ordena. Los contratos entre las piezas están en [contracts.md](contracts.md).
- **WhatsApp** pasa por una cola de Cloud Tasks (`app/lib/tasks.py`): el webhook valida la firma, encola un mensaje por tarea y responde 200; la cola llama a `/internal/whatsapp-task`, que corre el agente y responde por Kapso. Así hay reintentos y no se procesa dos veces el mismo mensaje. Detalle en [kapso.md](kapso.md).
- **MCP** llama directo a `search_all` (las fuentes de `search_offers` más la web abierta con Firecrawl), sin el agente, porque quien pregunta ya es un asistente de IA. Devuelve salida estructurada y un resumen en texto, y en Claude y ChatGPT se ve como un tablero de ofertas dentro del chat (MCP Apps, `app/ui/ofertas.html`). Detalle en [mcp-tool.md](mcp-tool.md).
- **La tasa** (`app/lib/rate.py`) es la oficial del BCV, que sirve dolarapi.com sin API key. Es lo único que convierte bolívares a dólares, y la usan la búsqueda, la web abierta, el catálogo y el MCP. Se guarda media hora en memoria; si la API no responde, se sigue con la última tasa buena y la fecha que viaja con cada precio dice de cuándo es.
- **El catálogo** (`app/lib/catalogo.py`, rutas `GET /catalogo/*` en `app/routes/catalogo.py`) arma las páginas públicas `/ve/...`: los modelos salen de `catalogo.json` y los precios, de `search_offers`.
- **`apps/web`** reenvía `/api/*` al backend con un rewrite de Next. Así el navegador habla con un solo dominio y no hace falta CORS. Ojo: `API_URL` se lee al **construir** la web, no al arrancarla.

## Qué hay y qué falta

| Pieza | Estado |
|---|---|
| Web con chat | Hecha |
| Orquestador y la web abierta | Hecho y probado por WhatsApp. Instagram y TikTok ya entran por Apify; Mercado Libre, Facebook y Meta Ads siguen apagados (`PAUSED_TOOLS`) |
| Webhook de WhatsApp | Hecho. El número de producción apunta al API en Cloud Run. Probado en el sandbox de Kapso |
| MCP con `search_prices` | Hecho, con íconos, instrucciones para el modelo y tablero de ofertas (MCP Apps) |
| Catálogo SEO (`/ve/...`) | Hecho con datos de ejemplo: 147 modelos, 28 categorías. Se indexa solo cuando hay ofertas reales: ver [seo-geo.md](seo-geo.md) |
| Confianza del comercio | Fórmula inicial en `apps/api/app/lib/prices.py`. Las cadenas con tienda propia, comparadas por dominio, están en `apps/api/app/lib/cadenas.py` ([sources.md](sources.md#cadenas-con-tienda-propia)). Los borradores por fuente (Instagram, Marketplace, TikTok, tiendas web, Mercado Libre, Amazon y Meta Ads) están en `resources/`, resumidos en [sources.md](sources.md#puntaje-de-confianza-por-fuente) |
| Tasa del dólar | Hecha: la oficial del BCV, de dolarapi.com |
| Fuentes reales | Firecrawl está conectado, fuera del registro de `search_offers`. Instagram y TikTok entran por Apify (`app/lib/sources/apify.py`), con `APIFY_TOKEN`: ver [sources.md](sources.md#apify-instagram-y-tiktok). Faltan Facebook Marketplace, Mercado Libre y Meta Ads |
| Deploy en GCP | Armado: `infra/` y `cloudbuild.*.yaml`. Cómo funciona, en [gcp.md](gcp.md) |

## Decisiones tomadas (2026-10-24)

- Agente con ADK y Gemini, Kapso y MCP en el backend. Web en Next.js, solo interfaz.
- Infraestructura en GCP, con Cloud Build para desplegar. Cloudflare solo maneja el DNS.
- Un orquestador (`root_agent`) y una tool por fuente de la pizarra ([resources/usaprais.com-agentic-architecture.pdf](../resources/usaprais.com-agentic-architecture.pdf)). Hoy corren la web abierta, Instagram y TikTok. Las demás tools están escritas y apagadas. El orquestador resume y es el único que habla con la persona.
- Las sesiones del agente viven en memoria. Si se pierden con un reinicio, no importa para la demo.
- **La tasa de referencia es la oficial del BCV**, no la paralela. Es la tasa legal, la de las facturas y las cadenas formales, y es la que se puede defender cuando alguien pregunta de dónde salió el número. La paralela está en el mismo proveedor (`/v1/dolares/paralelo`) si más adelante se quiere mostrar también.

> **Backend: de Fastify a Python (FastAPI).** El backend se reescribió en Python conservando los contratos: las mismas rutas (`/chat`, `/whatsapp`, `/mcp`, `/health`), las mismas formas de entrada y salida y las mismas reglas. Lo único que cambia son los nombres internos, por el lenguaje (`searchOffers` → `search_offers`, `askPrais` → `ask_prais`, `getRate` → `get_rate`, tipos en `snake_case`) y que una fuente ya no recibe un `AbortSignal`: la búsqueda la cancela a los 8 s. Lo decidió quien arma el backend y la infra. El detalle está en [contracts.md](contracts.md).

## Decisiones abiertas

1. Cómo se precalientan los actores de Apify. Hoy la primera búsqueda de un producto arranca la corrida y no la espera: la ve la segunda. Falta decidir si eso se programa (Cloud Scheduler) o se deja así.
2. De dónde salen las publicaciones de Instagram. Hoy se entra por el hashtag del producto, que es global; una lista de cuentas de comercios venezolanos daría mejores resultados.
3. Qué fuente se conecta después: Facebook Marketplace, Mercado Libre o Meta Ads.
4. Si hace falta base de datos. Por ahora no: los datos de ejemplo están en código.
