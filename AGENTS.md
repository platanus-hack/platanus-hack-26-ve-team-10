# Prais: guía para construir

Prais compara el precio de un producto en los principales canales de venta de Venezuela, califica la confianza de cada comercio y dice dónde está el mejor precio. Es un proyecto de hackathon: **lo más simple que funcione**. Una sola app de Next.js, un solo deploy en Cloud Run.

## Mapa del repo

| Ruta | Qué hay |
|---|---|
| `src/app/` | Páginas y rutas de la API: `/api/chat` (web), `/api/whatsapp` (Kapso) y `/api/mcp` (MCP) |
| `src/agent/` | El agente con ADK: instrucciones y tools |
| `src/lib/` | Tipos, búsqueda, precios, confianza y datos de ejemplo |
| `agents/` | Cómo se construye cada parte, un doc por área |
| `docs/` | Producto y decisiones |
| `resources/` | Material de referencia: fuentes candidatas, consultas de ejemplo |
| `design/brand/` | Marca: `lib.pen` (Pencil), logos y colores |

## Qué doc leer

| Si vas a tocar | Lee |
|---|---|
| Cualquier cosa, la primera vez | [agents/architecture.md](agents/architecture.md) y [agents/conventions.md](agents/conventions.md) |
| El agente o sus tools | [agents/adk.md](agents/adk.md) |
| Conectar una fuente real | [agents/sources.md](agents/sources.md) |
| WhatsApp | [agents/kapso.md](agents/kapso.md) |
| MCP | [agents/mcp-tool.md](agents/mcp-tool.md) |
| Páginas públicas | [agents/seo-geo.md](agents/seo-geo.md) |
| Deploy | [agents/gcp.md](agents/gcp.md) |

## Reglas

1. Todo cambio entra por PR a `main` del repo de la org, y el PR se mergea solo. No hagas push directo a `main` ni commits en `Pleo2/prais.com`.
2. El agente nunca inventa un precio: cada precio sale de `searchOffers`.
3. Todo precio que se muestra lleva su fuente y su fecha. Si se convirtió de moneda, también lleva la tasa usada.
4. Los secretos van en variables de entorno. Están listados en `.env.example`.
5. No toques `README.md`, `platanus-hack-project.jsonc`, `project-description.md` ni `project-logo.png` sin que te lo pidan, porque son la entrega de la hackathon.
6. No agregues servicios, paquetes ni capas hasta que una funcionalidad de la demo los necesite.

## Comandos

```bash
pnpm install
cp .env.example .env    # y pon GOOGLE_GENAI_API_KEY
pnpm dev                # http://localhost:3000
pnpm build && pnpm lint # antes de abrir el PR: no hay checks antes del auto-merge
```

## Antes de entregar

- [ ] Reescribir `project-description.md` con lo que Prais hace de verdad: hoy es provisional. Alinear también `project-description-spanish` en el `jsonc`.
- [ ] usaprais.com respondiendo, porque es la `deploy-url` que valida Platanus.
- [ ] `README.md` conciso, como pide Platanus.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
