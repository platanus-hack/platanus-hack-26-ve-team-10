@AGENTS.md

## Docs al día en cada commit

Este repo trae un hook de Claude Code en `.claude/settings.json` (script en `.claude/hooks/check-docs.mjs`). Se activa solo en cualquier PC que abra el repo con Claude Code, sin configurar nada. Necesita Node.

Antes de cada `git commit`, si el commit cambia código o configuración (`src/`, `package.json`, `next.config.ts`, `Dockerfile`, `.env.example`, `.github/`) y no toca los docs (`AGENTS.md`, `agents/`, `docs/`), el hook frena el commit. Entonces:

1. Revisa si el cambio afecta la arquitectura, una ruta, una variable de entorno, una dependencia o el deploy.
2. Si la afecta, actualiza `AGENTS.md` y el doc de `agents/` que corresponda, agrégalos con `git add` y repite el commit. Docs y código van en el mismo commit.
3. Si no hace falta tocar docs, repite el commit con `DOCS_REVIEWED=1` delante: `DOCS_REVIEWED=1 git commit -m "..."`.
