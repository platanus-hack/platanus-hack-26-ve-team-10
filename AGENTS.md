# Prais: guía para construir

Prais compara el precio de un producto en los principales canales de distribución de Venezuela, califica la confianza de cada comercio y dice dónde está el mejor precio en general. Este archivo es el mapa del repo. Léelo primero y después abre el doc de `agents/` del área que vas a tocar.

## Mapa del repo

| Ruta | Qué hay |
|---|---|
| `agents/` | Arquitectura y reglas para construir cada parte, un doc por área |
| `apps/web/` | Next.js: landing, blog, directorio, chat, dashboard y admin. Publica usaprais.com |
| `apps/agent/` | Agente de búsqueda inteligente con ADK para TypeScript: un orquestador y sus sub-agentes |
| `apps/ingest/` | Ingesta: recorre las fuentes y llena el índice de precios y comercios |
| `apps/whatsapp/` | Canal de WhatsApp con Kapso |
| `apps/mcp/` | Servidor MCP: Prais como herramienta para otros asistentes de IA |
| `packages/core/` | Dominio compartido: tipos, adapters de fuentes, monedas, ranking y confianza |
| `docs/` | Producto y decisiones: el porqué |
| `resources/` | Material de referencia: fuentes candidatas, consultas de ejemplo, investigación |
| `design/brand/` | Marca: `lib.pen` (librería en Pencil), logos y colores |

## Qué doc leer

| Si vas a tocar | Lee |
|---|---|
| Cualquier cosa, la primera vez | [agents/architecture.md](agents/architecture.md) y [agents/conventions.md](agents/conventions.md) |
| `apps/web` | [agents/web.md](agents/web.md), y [agents/seo-geo.md](agents/seo-geo.md) si es una página pública |
| `apps/agent` o `packages/core` | [agents/adk.md](agents/adk.md) |
| `apps/ingest` o un adapter de fuente | [agents/sources.md](agents/sources.md) |
| `apps/whatsapp` | [agents/kapso.md](agents/kapso.md) |
| `apps/mcp` | [agents/mcp-tool.md](agents/mcp-tool.md) |
| Deploy, Dockerfiles, secretos, GCP | [agents/gcp.md](agents/gcp.md) |

## Reglas que no se rompen

1. Todo cambio entra por PR a `main` del repo de la org, y el PR se mergea solo. No hagas push directo a `main` ni commits en `Pleo2/prais.com`.
2. La lógica de precios, monedas y confianza vive en `packages/core`. Las apps no calculan nada de eso por su cuenta.
3. Todo precio que se muestra lleva su moneda, su fuente y la fecha en que se vio. Si se convirtió, también lleva la tasa usada. Es la base de la confianza en Prais.
4. El agente nunca inventa un precio: cada precio de una respuesta sale del resultado de una tool. Si no puede confirmarlo, abre un caso en el human loop.
5. Los secretos van solo en variables de entorno (Secret Manager en GCP). Cada app documenta las suyas en `.env.example`.
6. No toques `README.md`, `platanus-hack-project.jsonc`, `project-description.md` ni `project-logo.png` sin que te lo pidan, porque son la entrega de la hackathon.
7. Si cambias la arquitectura, actualiza el doc de `agents/` en el mismo PR.

## Comandos

Usamos pnpm workspaces y Node 22.

```bash
pnpm install
pnpm --filter @prais/web dev
pnpm build && pnpm typecheck && pnpm lint
```

Todavía no hay validación antes del auto-merge. Corre `build`, `typecheck` y `lint` antes de abrir el PR.

## Antes de entregar

- [ ] Reescribir `project-description.md` con lo que Prais hace de verdad: hoy es provisional. Alinear también `project-description-spanish` en el `jsonc`.
- [ ] usaprais.com respondiendo, porque es la `deploy-url` que valida Platanus.
- [ ] `README.md` conciso, como pide Platanus.
