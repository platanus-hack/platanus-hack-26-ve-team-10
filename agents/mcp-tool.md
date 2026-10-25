# MCP

El servidor MCP es la ruta `/mcp` del backend (`apps/api/app/routes/mcp.py`), con transporte Streamable HTTP y sin sesiones. Usa el SDK de Python 2.x (`from mcp.server.mcpserver import MCPServer`; en la 1.x se llamaba `FastMCP`). Desde afuera queda en `https://usaprais.com/api/mcp`.

## Tools

| Tool | Entrada | Qué hace |
|---|---|---|
| `search_prices` | `query`, `zone?`, `needs_delivery?` | Llama a `search_all`: las fuentes de `search_offers` y la web abierta con Firecrawl, a la vez. Devuelve las ofertas ordenadas por precio en USD, con salida estructurada |

La tool llama directo a la búsqueda, sin el agente: quien pregunta ya es un asistente de IA, y así es más rápido y más barato. Los nombres y las descripciones van en inglés, que es lo que mejor entienden los clientes.

- **Salida estructurada.** La tool devuelve un `CallToolResult` con dos partes. `structuredContent` sigue el modelo `PriceSearch` (el cliente recibe su `outputSchema`): las claves de `search_offers` en camelCase, más `example`, `imageUrl` y `reviews` en cada oferta, y `exchangeRate` con la tasa para mostrar bolívares. `content` es un resumen en texto (`_summary`): el veredicto y hasta 10 ofertas, cada una con tienda, fecha y link. Es lo que lee el modelo y lo que ven los clientes sin widget.
- **Plazo.** La web abierta tiene 25 s dentro del MCP (`OPEN_WEB_BUDGET_S`). Si la búsqueda no llega, se responde sin ella y `firecrawl` aparece en `failedSources`. Si falla una página, la respuesta sigue con las demás: `firecrawl:<dominio>` aparece una vez por dominio cuando una página suya quedó bloqueada, dio error o no terminó a tiempo, y ese dominio no tiene ofertas en la respuesta; un link muerto (404 o 410) no cuenta.
- **Cache.** Firecrawl guarda cada producto en memoria (1 h si todo salió bien; las reglas están en [sources.md](sources.md)), así el mismo producto no gasta créditos dos veces. Un resultado cortado por el plazo de 25 s no se guarda, así que esa consulta vuelve a gastar créditos. Se pierde si Cloud Run reinicia la instancia.
- **Zona.** El filtro de zona no se aplica a la web abierta: casi ninguna tienda web dice su ciudad. Cuando un anuncio sí la dice (un portal de carros, por ejemplo), va en `merchant.zone`; si no, `merchant.zone` es `Venezuela`.

Para agregar una tool, decora una función `async` con `@mcp_server.tool(...)` en `app/routes/mcp.py`, o con `@apps.tool(resource_uri=...)` si muestra un widget. Si devuelve un modelo de pydantic con `structured_output=True`, el cliente recibe el schema.

## Identidad e instrucciones

- El servidor se llama `usaprais`, con `title`, `website_url` (`https://usaprais.com`) e íconos (el isotipo en PNG de 128 px y en SVG, como `data:` URI). Cada cliente decide dónde los muestra.
- `INSTRUCTIONS` le dice al modelo cómo usar la tool: pedir el modelo exacto si la consulta es vaga, empezar por el veredicto, citar tienda, fecha y tasa, no inventar nada y no repetir la lista cuando se ve el widget.

## Widget de ofertas (MCP Apps)

`search_prices` está enlazada a `ui://usaprais/ofertas.html` (`_meta.ui.resourceUri`). Claude y ChatGPT, que implementan [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview), muestran ese HTML dentro del chat, en un iframe aislado; los demás clientes usan el texto.

- **Archivos:** `apps/api/app/ui/ofertas.html`, más las copias del isotipo y de Prais (`pensando` y `ganga`) de `docs/design-system/assets`. La imagen de la API solo lleva `apps/api/app`, por eso son copias: si cambia la marca, hay que copiarlas de nuevo.
- **Qué muestra:** es un tablero de solo lectura; la búsqueda la hace el chat. Tiene el veredicto con Prais, cuatro cifras (más barato, más caro, ofertas y tiendas) y el ranking del más barato al más caro, con la más barata en amarillo. Cada oferta trae precio en USD y en Bs., tienda, canal, fecha y etiquetas de confianza y de ejemplo. Además hay un filtro por canal, que solo cambia la vista, las ofertas sin precio aparte, las tiendas que no respondieron y la tasa usada. Sigue la capa de producto del [design system](../docs/design-system/README.md) y el tema claro u oscuro del host.
- **Qué hace:** abre cada oferta con `ui/open-link`. No llama tools por su cuenta.
- **Protocolo:** JSON-RPC sobre `postMessage`, sin dependencias: `ui/initialize`, `ui/notifications/initialized` y después recibe `ui/notifications/tool-input` y `tool-result`. Avisa su alto con `ui/notifications/size-changed`. La especificación está en [ext-apps](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx).
- **Seguridad:** el texto de las ofertas viene de páginas de terceros, así que el widget lo pinta con `textContent`, nunca como HTML, y solo acepta links `http(s)`.
- **CSP:** solo declara Google Fonts. Las fotos de las tiendas vienen de dominios que no se conocen de antemano: si el host no las deja cargar, el widget muestra la inicial de la tienda.

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

El widget se ve en el inspector (pestaña Apps) o desde Claude con el conector apuntando a la URL pública.
