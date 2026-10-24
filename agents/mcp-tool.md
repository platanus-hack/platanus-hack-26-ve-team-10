# MCP tool: apps/mcp

Expone la búsqueda de Prais como tools de MCP. Así cualquier asistente que hable MCP (Claude, ChatGPT, Cursor...) puede preguntar dónde está el mejor precio en Venezuela.

## Cómo está hecho

- Un servicio de Cloud Run sin estado, en `https://mcp.usaprais.com/mcp`.
- Usa `McpServer` y el transporte Streamable HTTP de `@modelcontextprotocol/sdk`, en modo sin sesión. SSE está deprecado.
- Crea un servidor nuevo por request.
- Las tools llaman a `POST /search` del agente con `channel: "mcp"`. Así los resultados son los mismos que en la web y en WhatsApp.

## Tools

| Tool | Entrada | Salida |
|---|---|---|
| `search_prices` | `query: string`, `zone?: string`, `max_results?: number` | Mejor oferta y lista de ofertas, con la confianza de cada comercio |
| `get_merchant` | `merchant_id: string` | Perfil del comercio y su puntaje de confianza |
| `get_exchange_rates` | nada | Tasas que usa Prais, con fuente y fecha |

- Los nombres van en `snake_case` y las descripciones en inglés, que es lo que mejor entienden los clientes. Di en la descripción que los precios son de Venezuela.
- Si el agente devuelve `kind: "question"`, la tool la devuelve como texto, para que el asistente se la pase al usuario.
- Cada oferta trae su fuente, su precio original, el precio en USD, la tasa usada, la fecha y el enlace. Devuélvela como texto breve y como `structuredContent`.
- Los argumentos se validan con zod 4.

## Seguridad y costos

- Por ahora es pública y de solo lectura.
- Cada llamada le cuesta tokens al agente. Limita las instancias de Cloud Run y pon un límite de requests por IP en el servicio.

## Probar

```bash
npx @modelcontextprotocol/inspector
```

Conéctalo a `http://localhost:8080/mcp` o a la URL publicada.

## Docs

- [Especificación de MCP: transportes](https://modelcontextprotocol.io/specification/latest/basic/transports)
- [SDK de TypeScript](https://github.com/modelcontextprotocol/typescript-sdk)
