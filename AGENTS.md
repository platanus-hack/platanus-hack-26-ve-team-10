# Prais: guía para construir

Prais compara el precio de un producto en los principales canales de venta de Venezuela, califica la confianza de cada comercio y dice dónde está el mejor precio. Es un proyecto de hackathon: **rápido, simple y claro**. Nada de boilerplate ni de capas que la demo no necesite.

## Mapa del repo

| Ruta | Qué hay |
|---|---|
| `apps/api/` | Backend en Fastify: el agente ADK, el webhook de Kapso y el servidor MCP |
| `apps/api/src/lib/` | Tipos y contratos, búsqueda, precios, confianza y tasa. Es la única fuente de esa lógica |
| `apps/api/src/lib/sources/` | Una fuente por archivo (hoy, la de ejemplo), registradas en `index.ts` |
| `apps/web/` | Next.js: solo la interfaz. Su `/api/*` se reenvía al backend |
| `agents/` | Cómo se construye cada parte, un doc por área |
| `docs/design-system/` | Design system de usaprais: tokens y componentes para la web. Léelo antes de tocar la interfaz |
| `docs/`, `resources/`, `design/brand/` | Decisiones, material de referencia y marca (`lib.pen`) |

## Qué doc leer

| Si vas a tocar | Lee |
|---|---|
| Cualquier cosa, la primera vez | [agents/architecture.md](agents/architecture.md), [agents/contracts.md](agents/contracts.md) y [agents/conventions.md](agents/conventions.md) |
| Qué hace cada uno del equipo | [docs/plan.md](docs/plan.md) |
| Usar una API o librería externa (ADK, Kapso, Firecrawl, Apify, Mercado Libre, Fastify, Next, Gemini) | [agents/tools.md](agents/tools.md): su skill, su MCP o su `llms.txt` |
| El agente o sus tools | [agents/adk.md](agents/adk.md) |
| Conectar una fuente real | [agents/sources.md](agents/sources.md) |
| WhatsApp | [agents/kapso.md](agents/kapso.md) |
| MCP | [agents/mcp-tool.md](agents/mcp-tool.md) |
| Páginas públicas | [agents/seo-geo.md](agents/seo-geo.md) |
| Deploy | [agents/gcp.md](agents/gcp.md) |

## Reglas

1. `main` está bloqueado: todo cambio entra por PR a `main` del repo de la org, y el PR se mergea solo. Nunca hagas push a `main`.
2. Todo se sube en paralelo a Platanus y a `Pleo2/usaprais.com`. `pnpm install` lo configura y los hooks lo exigen. Después de cada merge, `pnpm sync`.
3. **No te repitas.** La lógica de precios vive solo en `apps/api/src/lib`. La web no calcula nada: le pregunta al backend.
4. **Sin boilerplate.** Antes de agregar un archivo, una capa o un paquete, piensa si la demo lo necesita hoy. Si no, no va.
5. **No adivines APIs externas.** Antes de escribir contra una, consulta su skill, su MCP o su `llms.txt` ([agents/tools.md](agents/tools.md)).
6. El agente nunca inventa un precio: cada precio sale de `searchOffers`.
7. Todo precio que se muestra lleva su fuente y su fecha. Si se convirtió de moneda, también lleva la tasa usada.
8. Los secretos van en variables de entorno, listadas en el `.env.example` de cada app.
9. No toques `README.md`, `platanus-hack-project.jsonc`, `project-description.md` ni `project-logo.png` sin que te lo pidan, porque son la entrega de la hackathon.

## Comandos

```bash
pnpm install                             # también configura git: hooks y push en paralelo a Platanus y usaprais.com
cp apps/api/.env.example apps/api/.env   # pon GOOGLE_GENAI_API_KEY
pnpm dev                                 # api en :4000, web en :3000
git pull origin main                     # antes del PR: trae lo último de main a tu rama
pnpm build && pnpm lint                  # y vuelve a probar: no hay checks antes del auto-merge
pnpm sync                                # después del merge: copia main de Platanus a usaprais.com
```

## Antes de entregar

- [ ] Reescribir `project-description.md` con lo que Prais hace de verdad: hoy es provisional. Alinear también `project-description-spanish` en el `jsonc`.
- [ ] Deploy en GCP armado (dev a cargo de GCP, ver [agents/gcp.md](agents/gcp.md)) y usaprais.com respondiendo, porque es la `deploy-url` que valida Platanus.
- [ ] `README.md` conciso, como pide Platanus.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
