# Herramientas para agentes: MCP y docs oficiales

Antes de escribir código contra una API externa, consulta su documentación oficial en vez de adivinarla. Si el producto tiene un MCP, úsalo. Si no, lee su `llms.txt`.

## MCP del repo (`.mcp.json`)

Claude Code los carga al abrir el repo. La primera vez pide aprobarlos, y los que usan OAuth piden iniciar sesión con `/mcp`.

| MCP | Para qué | Auth |
|---|---|---|
| `kapso-docs` | Buscar en la documentación de Kapso y WhatsApp | Ninguna |
| `kapso` | Operar el proyecto de Kapso: números, webhooks, conversaciones, plantillas | OAuth (solo lectura por defecto) o API key |
| `firecrawl` | Scrapear y buscar en webs de tiendas mientras desarrollas el adapter | Sin key: `scrape` y `search`, con límite. Con key: todo |
| `apify` | Buscar actores (Instagram, TikTok, Marketplace), probarlos y leer sus datasets | OAuth o `APIFY_TOKEN` |
| `next-devtools` | Errores, rutas y logs de la web corriendo con `pnpm dev` (Next 16+) | Ninguna |

## Se agregan a mano (necesitan credenciales propias)

| MCP | Cómo | Para qué |
|---|---|---|
| Mercado Libre | `claude mcp add --transport http mercadolibre https://mcp.mercadolibre.com/mcp --header "Authorization: Bearer <token>"`. El token sale de la app registrada en Mercado Libre | Consultar sus APIs: frente 3 de [docs/plan.md](../docs/plan.md) |
| Google Developer Knowledge | Endpoint `https://developerknowledge.googleapis.com/mcp`. Se habilita en el proyecto de GCP y usa autenticación de Google Cloud. Está en preview | Docs oficiales de Google: ADK (`adk.dev`), Gemini (`ai.google.dev`), Cloud Run |
| Cloud Run | MCP remoto de Google Cloud, con OAuth e IAM (no acepta API keys) | Deploy: lo decide el dev de GCP |

## Docs para LLMs (`llms.txt`)

Si no hay MCP, o para leer la documentación entera, abre el índice con WebFetch:

| Tecnología | Índice |
|---|---|
| ADK (agentes) | https://adk.dev/llms.txt |
| Gemini API | https://ai.google.dev/gemini-api/docs/llms.txt |
| Fastify | https://fastify.dev/llms.txt |
| Next.js | La doc de la versión instalada está en `node_modules/next/dist/docs/` (más fiel que la web). Índice web: https://nextjs.org/docs/llms.txt |
| MCP (protocolo y SDK) | https://modelcontextprotocol.io/llms.txt |
| Kapso | https://docs.kapso.ai/llms.txt |
| Firecrawl | https://docs.firecrawl.dev/llms.txt |
| Apify | https://docs.apify.com/llms.txt |
| Cloudflare (DNS) | https://developers.cloudflare.com/llms.txt |

Tailwind, pnpm y Cloud Run no publican `llms.txt`: usa su web o el MCP de Google para Cloud Run.

## Ojo

- Los MCP que operan cuentas reales (`kapso`, `apify`, Mercado Libre) pueden mandar mensajes o gastar créditos. Úsalos para explorar y configurar. Lo que va a producción vive en el código de `apps/api`.
- No pegues keys en `.mcp.json`: se sube al repo. Las credenciales van en el login OAuth o en `claude mcp add` local.
