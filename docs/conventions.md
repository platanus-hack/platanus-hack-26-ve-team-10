# Convenciones

## Idioma

- Docs, interfaz y mensajes al usuario: en español de Venezuela.
- Código, identificadores, commits y títulos de PR: en inglés. Los commits siguen [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `ci:`.

## Ramas y PRs

`main` está bloqueado: nadie hace push directo, todo entra por PR. GitHub no nos deja proteger la rama (no somos admins del repo), así que lo frena el hook de git (`.githooks/pre-push`): un push a `main` de Platanus se rechaza, y hacia `Pleo2/usaprais.com` se permite (`pnpm sync`).

### Sincronización con usaprais.com

Todo se sube en paralelo al repo de Platanus y a `Pleo2/usaprais.com`:

- **Automático:** `pnpm install` corre `pnpm setup:git`, que activa los hooks y le pone a `origin` dos URLs de push. Así cada `git push` de una rama llega a los dos repos.
- **Obligatorio:** si un clon no sube a los dos repos, los hooks frenan el push y piden correr `pnpm setup:git`.
- **Nunca mergees PRs en `usaprais.com`:** GitHub no deja proteger ese repo en el plan actual, así que la regla depende del equipo.
- **Después de cada merge:** `pnpm sync`. Copia el `main` de Platanus a `usaprais.com`. Es el único push a `main` que permiten los hooks.

1. Crea la rama desde `main` actualizado, con el nombre `<tipo>/<tema-corto>`. Por ejemplo, `feat/whatsapp-webhook`.
2. Abre el PR a `main` del repo de la org. `.github/workflows/auto-merge.yml` lo mergea solo, con merge commit y sin squash, para que se conserven los commits y autores de cada uno.
3. Si el PR no está listo, ábrelo como borrador: los borradores no se mergean.
4. Antes de abrir el PR, trae lo último de `main` a tu rama (`git pull origin main`), corre `pnpm install` si cambió el lockfile y vuelve a correr `pnpm build && pnpm lint && pnpm test`. No hay checks antes del auto-merge: lo que entra es lo que probaste.

## Deploy

Cómo funciona, en [gcp.md](gcp.md).

## Código

- `apps/web`: TypeScript en modo `strict`, y `@/` apunta a `src/`.
- `apps/api`: Python 3.12, con `ruff` (`pnpm lint`). Los imports internos son `app.*`.
- Pruebas de `apps/api`: `unittest` de la librería estándar, en `apps/api/tests/` (`pnpm test`). Sin red ni créditos: las APIs externas se reemplazan por un cliente falso.
- Toda entrada externa se valida: en `apps/api` con pydantic (bodies de las rutas y argumentos de tools); los webhooks, con la firma y el JSON esperado.
- Los secretos van en `.env`, que nunca se sube, y se listan en `.env.example`. En GCP van en Secret Manager.
- Fija versiones exactas en `apps/api/requirements.txt` (`google-adk`, `mcp`, los SDKs de las fuentes): cambian rápido.
- Lo simple primero: nada de paquetes, servicios o capas nuevas hasta que la demo los necesite.

## Docs

- `docs/`: toda la documentación. El mapa para saber cuál leer está en `AGENTS.md`.
- Cada decisión con matices va en `docs/decisions/NNNN-titulo.md`.
- `resources/`: material de referencia, no instrucciones.
- Si un cambio contradice un doc, actualiza ese doc en el mismo commit. El hook `.githooks/pre-commit` frena un commit de código que no toca `docs/` ni `AGENTS.md`, salvo que vaya precedido de `DOCS_REVIEWED=1`. Cursor aplica la misma regla antes de ejecutar `git commit` (`.cursor/hooks.json`).

## Archivos de la entrega

`README.md`, `platanus-hack-project.jsonc`, `project-description.md` y `project-logo.png` son lo que revisa Platanus. Solo se tocan cuando alguien del equipo lo pide.
