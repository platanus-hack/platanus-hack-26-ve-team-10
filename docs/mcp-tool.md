# MCP

El servidor MCP es la ruta `/mcp` del backend (`apps/api/app/routes/mcp.py`), con transporte Streamable HTTP y sin sesiones. Usa el SDK de Python 2.x (`from mcp.server.mcpserver import MCPServer`; en la 1.x se llamaba `FastMCP`). Desde afuera queda en `https://usaprais.com/api/mcp`.

## Tools

| Tool | Entrada | Qué hace |
|---|---|---|
| `search_prices` | `query`, `zone?`, `needs_delivery?` | Llama a `search_all`: las fuentes de `search_offers` y la web abierta con Firecrawl, a la vez. Devuelve las ofertas ordenadas por precio en USD, con salida estructurada |

La tool llama directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA, y así es más rápido y más barato. Los nombres y las descripciones van en inglés, que es lo que mejor entienden los clientes.

- **Salida estructurada.** La tool devuelve un modelo de pydantic (`PriceSearch`), y el cliente recibe su `outputSchema` y un `structuredContent`. Las claves son las de `search_offers`, en camelCase, más `example` en cada oferta. El SDK también manda el mismo JSON como texto, para los clientes que no leen la salida estructurada.
- **Plazo.** La web abierta tiene 25 s dentro del MCP (`OPEN_WEB_BUDGET_S`). Si la búsqueda no llega, se responde sin ella y `firecrawl` aparece en `failedSources`. Si falla una página, la respuesta sigue con las demás: `firecrawl:<dominio>` aparece una vez por dominio cuando una página suya quedó bloqueada, dio error o no terminó a tiempo, y ese dominio no tiene ofertas en la respuesta; un link muerto (404 o 410) no cuenta.
- **Cache.** Firecrawl guarda cada producto en memoria (1 h si todo salió bien; las reglas están en [sources.md](sources.md)), así el mismo producto no gasta créditos dos veces. Un resultado cortado por el plazo de 25 s no se guarda, así que esa consulta vuelve a gastar créditos. Se pierde si Cloud Run reinicia la instancia.
- **Zona.** El filtro de zona no se aplica a la web abierta: casi ninguna tienda web dice su ciudad. Cuando un anuncio sí la dice (un portal de carros, por ejemplo), va en `merchant.zone`; si no, `merchant.zone` es `Venezuela`.

Para agregar una tool, decora una función `async` con `@mcp_server.tool(...)` en `app/routes/mcp.py`. Si devuelve un modelo de pydantic con `structured_output=True`, el cliente recibe el schema.

## Conectarlo

| Cliente | Cómo |
|---|---|
| Claude | Configuración → Conectores → Agregar conector personalizado, con la URL de arriba y sin inicio de sesión. Funciona en todos los planes |
| ChatGPT | Servidor MCP personalizado: solo en Business, Enterprise y Edu (en Pro, solo tools de lectura, como esta) |
| Grok | Por la API de xAI, como tool `mcp` con `server_url` |
| Gemini CLI | `gemini mcp add --transport http usaprais https://usaprais.com/api/mcp` |

La primera llamada después de un rato sin uso tarda unos 17 s: es el arranque en frío de Cloud Run.

## Probar

```bash
pnpm dev
npx @modelcontextprotocol/inspector   # conectar a http://localhost:4000/mcp
```
