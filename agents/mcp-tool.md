# MCP

El servidor MCP es la ruta `/mcp` del backend (`apps/api/app/routes/mcp.py`), con transporte Streamable HTTP y sin sesiones. Usa el SDK de Python 2.x (`from mcp.server.mcpserver import MCPServer`; en la 1.x se llamaba `FastMCP`). Desde afuera queda en `https://usaprais.com/api/mcp`.

## Tools

| Tool | Entrada | Qué hace |
|---|---|---|
| `search_prices` | `query`, `zone?`, `needs_delivery?` | Llama a `search_offers` y devuelve las ofertas en JSON |

La tool llama directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA, y así es más rápido y más barato. Los nombres y las descripciones van en inglés, que es lo que mejor entienden los clientes.

Para agregar una tool, decora una función `async` con `@mcp_server.tool(...)` en `app/routes/mcp.py`.

## Probar

```bash
pnpm dev
npx @modelcontextprotocol/inspector   # conectar a http://localhost:4000/mcp
```
