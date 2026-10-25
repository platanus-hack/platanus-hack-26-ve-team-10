# Prais: guía para construir

Prais compara el precio de un producto en los principales canales de venta de Venezuela, califica la confianza de cada comercio y dice dónde está el mejor precio. Es un proyecto de hackathon: **rápido, simple y claro**. Nada de boilerplate ni de capas que la demo no necesite.

## Mapa del repo

| Ruta | Qué hay |
|---|---|
| `services/api/` | Backend en Python (FastAPI): el agente ADK, el webhook de Kapso y el servidor MCP |
| `services/api/app/lib/` | Tipos y contratos, búsqueda, precios, confianza y tasa. Es la única fuente de esa lógica |
| `services/api/app/lib/sources/` | Fuentes del registro: la de ejemplo (`mock.py`) e Instagram y TikTok por Apify (`apify.py`). Firecrawl no está en el registro: vive en `firecrawl.py` y se llama directo. Amazon (`amazon.py`) tampoco: lo llama la tool de importación |
| `services/api/app/agents/` | Código del orquestador y de sus tools. No es documentación |
| `infra/`, `cloudbuild.*.yaml` | Scripts de `gcloud` y pipelines de Cloud Build |
| `services/web/` | Next.js: solo la interfaz. Su `/api/*` se reenvía al backend |
| `docs/` | Toda la documentación. El índice está en [docs/README.md](docs/README.md) |
| `resources/` | Material de referencia. No son instrucciones |

## Qué doc leer

La documentación vive en `docs/`. Entra por la fila del área que vas a tocar.

| Si vas a tocar | Lee |
|---|---|
| Cualquier cosa, la primera vez | [docs/architecture.md](docs/architecture.md), [docs/contracts.md](docs/contracts.md) y [docs/conventions.md](docs/conventions.md) |
| Ramas, PRs, el push a los dos repos, idioma y estilo de código | [docs/conventions.md](docs/conventions.md) |
| CI: el auto-merge y qué hay que probar antes del PR | [docs/conventions.md](docs/conventions.md) y `.github/workflows/auto-merge.yml` |
| Infra y deploy (GCP, Cloud Build, Cloud Run, secretos) | [docs/gcp.md](docs/gcp.md) y [infra/README.md](infra/README.md) |
| Una API o librería externa (ADK, Kapso, Firecrawl, Apify, Mercado Libre, FastAPI, Next, Gemini) | [docs/tools.md](docs/tools.md): su skill, su MCP o su `llms.txt` |
| El agente o sus tools | `services/api/app/agents/orchestrator.py` y `services/api/app/agent.py` |
| Si una tienda de la web abierta se puede recomendar | `services/api/app/agents/open_web_trust_skill.md`. El cálculo estricto sigue en `resources/website_trust_score.py` |
| Conectar una fuente real | [docs/sources.md](docs/sources.md) |
| El puntaje de confianza | `services/api/app/lib/trust.py`, `services/api/app/lib/contracts.py` y los borradores de `resources/*_trust_score.py` |
| WhatsApp | [docs/kapso.md](docs/kapso.md) |
| MCP | [docs/mcp-tool.md](docs/mcp-tool.md) |
| Páginas públicas | [docs/seo-geo.md](docs/seo-geo.md), y el detalle en [docs/ficha-producto.md](docs/ficha-producto.md), [docs/categoria.md](docs/categoria.md) y [docs/marca.md](docs/marca.md) |
| La interfaz | [docs/design-system/](docs/design-system/) antes de tocar componentes, tokens o al personaje |

## Reglas

1. `main` está bloqueado: todo cambio entra por PR a `main` del repo de la org, y el PR se mergea solo. Nunca hagas push a `main`.
2. Todo se sube en paralelo a Platanus y a `Pleo2/usaprais.com`. `pnpm install` lo configura y los hooks lo exigen. Después de cada merge, `pnpm sync`.
3. **No te repitas.** La lógica de precios vive solo en `services/api/app/lib`. La web no calcula nada: le pregunta al backend.
4. **Sin boilerplate.** Antes de agregar un archivo, una capa o un paquete, piensa si la demo lo necesita hoy. Si no, no va.
5. **No adivines APIs externas.** Antes de escribir contra una, consulta su skill, su MCP o su `llms.txt` ([docs/tools.md](docs/tools.md)).
6. El agente nunca inventa un precio. Cada precio sale de `search_offers` o de `search_open_web`.
7. Todo precio que se muestra lleva su fuente y su fecha. Si se convirtió de moneda, también lleva la tasa usada.
8. Los secretos van en variables de entorno, listadas en el `.env.example` de cada app.
9. No toques `README.md`, `platanus-hack-project.jsonc`, `project-description.md` ni `project-logo.png` sin que te lo pidan, porque son la entrega de la hackathon.
10. **Docs en el mismo commit.** Si el cambio toca código o configuración (`app/` o `src/` de una app, `requirements.txt`, `package.json`, `next.config.ts`, `Dockerfile`, `.env.example`, `pnpm-workspace.yaml`, `infra/`, `cloudbuild.*.yaml` o `.github/`), el commit también tiene que tocar `AGENTS.md` o `docs/`. Antes, revisa si cambió la arquitectura, una ruta, una variable de entorno, una dependencia o el deploy, y actualiza el doc de la tabla de arriba. Si no hace falta, repite el commit con `DOCS_REVIEWED=1` delante. Lo exigen `.githooks/pre-commit` (cualquier `git commit`, después de `pnpm install`) y `.cursor/hooks.json` (Cursor, antes de ejecutar el commit).
11. **Un commit por turno.** En Cursor, si un turno deja archivos cambiados, el hook `stop` de `.cursor/hooks.json` pide un commit antes de seguir. Un turno, un commit. No juntes el trabajo de varios turnos en uno solo.

## Comandos

```bash
pnpm install                             # también configura git: hooks y push en paralelo a Platanus y usaprais.com
cp services/api/.env.example services/api/.env   # pon GOOGLE_GENAI_API_KEY
pnpm dev                                 # api en :4000, web en :3000 (la primera vez crea services/api/.venv: pide python3)
git pull origin main                     # antes del PR: trae lo último de main a tu rama
pnpm build && pnpm lint && pnpm test     # y vuelve a probar: no hay checks antes del auto-merge
pnpm sync                                # después del merge: copia main de Platanus a usaprais.com
```

## Antes de entregar

- [ ] Reescribir `project-description.md` con lo que Prais hace de verdad: hoy es provisional. Alinear también `project-description-spanish` en el `jsonc`.
- [ ] Deploy en GCP armado (dev a cargo de GCP, ver [docs/gcp.md](docs/gcp.md)) y usaprais.com respondiendo, porque es la `deploy-url` que valida Platanus.
- [ ] `README.md` conciso, como pide Platanus.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
