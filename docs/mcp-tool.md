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
