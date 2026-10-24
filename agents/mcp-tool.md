# MCP

El servidor MCP es la ruta `/mcp` del backend (`apps/api/src/routes/mcp.ts`), con transporte Streamable HTTP y sin sesiones. Desde afuera queda en `https://usaprais.com/api/mcp`.

## Tools

| Tool | Entrada | Qué hace |
|---|---|---|
| `search_prices` | `query`, `zone?`, `needs_delivery?` | Llama a `searchOffers` y devuelve las ofertas en JSON |

La tool llama directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA, y así es más rápido y más barato. Los nombres y las descripciones van en inglés, que es lo que mejor entienden los clientes.

Para agregar una tool, súmala con `server.registerTool` dentro de `createServer()`.

## Probar

```bash
pnpm dev
npx @modelcontextprotocol/inspector   # conectar a http://localhost:4000/mcp
```
