# MCP

El servidor está en `services/api/app/routes/mcp.py`, montado en `/mcp`. Desde afuera queda en `https://usaprais.com/api/mcp`.

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

El tablero (`services/api/app/ui/ofertas.html`) se ve en el inspector, pestaña Apps, o en Claude y ChatGPT con el conector apuntando a la URL pública.

## Solo transporte y una skill

El MCP no tiene búsqueda propia. `search_prices` llama a `find_all_listings` (`app/agents/specialists.py`), que corre lo mismo que las tools del orquestador en un turno: la web abierta, el registro (Mercado Libre, Facebook Marketplace, Instagram y TikTok) una sola vez y traerlo de USA. Después cierra la confianza con `close_listings`. Así una tienda tiene el mismo puntaje en WhatsApp y en Claude o ChatGPT. `mcp.py` solo traduce esas tarjetas a la salida estructurada (`merchant.trust`, `merchant.stars`, `merchant.verdict`, `priceKind`).

Cómo contestar va en la skill, que el servidor manda como `instructions`: [`app/routes/mcp_skill.md`](../services/api/app/routes/mcp_skill.md), que incluye [`app/agents/trust_skill.md`](../services/api/app/agents/trust_skill.md), la misma que lee el orquestador. Para cambiar cómo responde el asistente, se edita la skill, no el código.

La web abierta tiene 25 s en el MCP; Amazon espera hasta 35 s, así que una llamada puede tardar unos 40 s.
