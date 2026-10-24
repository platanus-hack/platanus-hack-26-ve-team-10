# Herramientas para agentes: skills, MCP y docs oficiales

Antes de escribir código contra una API externa, consulta su documentación oficial en vez de adivinarla. El orden es: el skill del producto, después su MCP y, si no hay, su `llms.txt`.

## Skills y plugins

Se activan solos al abrir el repo con Claude Code. La primera vez, Claude Code pide instalar los plugins del proyecto.

| Skill o plugin | Qué trae | Dónde |
|---|---|---|
| **Apify** (plugin oficial) | Skills para usar y construir actores, un agente que elige el actor correcto y el MCP de Apify (OAuth con `/mcp`) | `.claude/settings.json` |
| **Firecrawl** (plugin oficial) | Skills para buscar en la web y en docs de desarrollo, y el MCP de búsqueda de Firecrawl. `/firecrawl:setup` pide la key | `.claude/settings.json` |
| **Fastify** | Buenas prácticas de Fastify. **Ya no aplica**: el backend pasó a FastAPI (Python). Queda en el repo, sin uso | `.claude/skills/fastify/`, copiado de [mcollina/skills](https://github.com/mcollina/skills) (MIT) |
| **Kapso** (oficial) | Integrar WhatsApp, automatizarlo y depurar webhooks | No viene en el repo, porque no tiene licencia publicada. Cada uno lo instala con `npx skills add gokapso/agent-skills` |

Sin skill propio:
- **Next.js:** su doc viene con la versión instalada (`node_modules/next/dist/docs/`), y está el MCP `next-devtools`.
- **ADK para Python:** los skills de Google (`google/agents-cli`) apuntan sobre todo a ADK en Python, que es el que usamos. Para la API exacta, usa el `llms.txt` de ADK y la firma de las clases en el paquete instalado.
- **FastAPI:** sin skill en el repo. Usa su documentación web.

## MCP del repo (`.mcp.json`)

Claude Code los carga al abrir el repo. La primera vez pide aprobarlos, y los que usan OAuth piden iniciar sesión con `/mcp`.

| MCP | Para qué | Auth |
|---|---|---|
| `kapso-docs` | Buscar en la documentación de Kapso y WhatsApp | Ninguna |
| `kapso` | Operar el proyecto de Kapso: números, webhooks, conversaciones, plantillas | OAuth (solo lectura por defecto) o API key |
| `firecrawl` | Scrapear y buscar en webs de tiendas mientras desarrollas el adapter | Sin key: `scrape` y `search`, con límite. Con key: todo |
| `next-devtools` | Errores, rutas y logs de la web corriendo con `pnpm dev` (Next 16+) | Ninguna |

## Se agregan a mano (necesitan credenciales propias)

| MCP | Cómo | Para qué |
|---|---|---|
| Mercado Libre | `claude mcp add --transport http mercadolibre https://mcp.mercadolibre.com/mcp --header "Authorization: Bearer <token>"`. El token sale de la app registrada en Mercado Libre | Consultar sus APIs: frente 3 de [docs/plan.md](../docs/plan.md) |
| Google Developer Knowledge | Endpoint `https://developerknowledge.googleapis.com/mcp`. Se habilita en el proyecto de GCP y usa autenticación de Google Cloud. Está en preview | Docs oficiales de Google: ADK (`adk.dev`), Gemini (`ai.google.dev`), Cloud Run |
| Cloud Run | MCP remoto de Google Cloud, con OAuth e IAM (no acepta API keys) | Deploy: ver [gcp.md](gcp.md) |

## Docs para LLMs (`llms.txt`)

Si no hay MCP, o para leer la documentación entera, abre el índice con WebFetch:

| Tecnología | Índice |
|---|---|
| ADK (agentes, Python) | https://adk.dev/llms.txt |
| Gemini API | https://ai.google.dev/gemini-api/docs/llms.txt |
| FastAPI | https://fastapi.tiangolo.com (no confirmamos que publique `llms.txt`) |
| Next.js | La doc de la versión instalada está en `node_modules/next/dist/docs/` (más fiel que la web). Índice web: https://nextjs.org/docs/llms.txt |
| MCP (protocolo) | https://modelcontextprotocol.io/llms.txt |
| MCP: SDK de Python (2.x) | https://py.sdk.modelcontextprotocol.io/ |
| Kapso | https://docs.kapso.ai/llms.txt |
| Firecrawl | https://docs.firecrawl.dev/llms.txt |
| Apify | https://docs.apify.com/llms.txt |
| Cloudflare (DNS) | https://developers.cloudflare.com/llms.txt |

Tailwind, pnpm y Cloud Run no publican `llms.txt`: usa su web o el MCP de Google para Cloud Run.

## Ojo

- Los MCP que operan cuentas reales (`kapso`, `apify`, Mercado Libre) pueden mandar mensajes o gastar créditos. Úsalos para explorar y configurar. Lo que va a producción vive en el código de `apps/api`.
- No pegues keys en `.mcp.json`: se sube al repo. Las credenciales van en el login OAuth o en `claude mcp add` local.
