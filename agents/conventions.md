# Convenciones

## Idioma

- Docs, interfaz y mensajes al usuario: en español de Venezuela.
- Código, identificadores, commits y títulos de PR: en inglés. Los commits siguen [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `ci:`.

## Ramas y PRs

`main` está bloqueado: nadie hace push directo, todo entra por PR. GitHub no nos deja proteger la rama (no somos admins del repo), así que lo frenan dos hooks: el de Claude Code (`.claude/hooks/guard-main.mjs`) y el de git (`.githooks/pre-push`).

### Sincronización con prais.com

Todo se sube en paralelo al repo de Platanus y a `Pleo2/prais.com`:

- **Una vez por clon:** `pnpm setup:git`. Activa los hooks y le pone a `origin` dos URLs de push, así cada `git push` de una rama llega a los dos repos.
- **Después de cada merge:** `pnpm sync`. Copia el `main` de Platanus a `prais.com`. Es el único push a `main` que permiten los hooks.

1. Crea la rama desde `main` actualizado, con el nombre `<tipo>/<tema-corto>`. Por ejemplo, `feat/whatsapp-webhook`.
2. Abre el PR a `main` del repo de la org. `.github/workflows/auto-merge.yml` lo mergea solo, con merge commit y sin squash, para que se conserven los commits y autores de cada uno.
3. Si el PR no está listo, ábrelo como borrador: los borradores no se mergean.
4. Antes de abrir el PR, trae lo último de `main` a tu rama (`git pull origin main`), corre `pnpm install` si cambió el lockfile y vuelve a correr `pnpm build && pnpm lint`. No hay checks antes del auto-merge: lo que entra es lo que probaste.

## Deploy

Pendiente: lo arma el dev a cargo de GCP. Ver los requisitos en [gcp.md](gcp.md).

## Código

- TypeScript en modo `strict`. En `apps/api` los imports internos llevan `.js` (ESM de Node); en `apps/web`, `@/` apunta a `src/`.
- Toda entrada externa se valida con zod 4: bodies de las rutas, webhooks y argumentos de tools.
- Los secretos van en `.env`, que nunca se sube, y se listan en `.env.example`. En GCP van en Secret Manager.
- Fija versiones exactas de `@google/adk` y de los SDKs de las fuentes: cambian rápido.
- Lo simple primero: nada de paquetes, servicios o capas nuevas hasta que la demo los necesite.

## Docs

- `agents/`: cómo se construye cada parte. Lo leen las personas y los agentes de código. Cortos, y solo sobre lo que existe.
- `docs/`: producto y decisiones. Cada decisión con matices va en `docs/decisions/NNNN-titulo.md`.
- `resources/`: material de referencia, no instrucciones.
- Si un cambio contradice un doc de `agents/`, actualiza el doc en el mismo PR.

## Archivos de la entrega

`README.md`, `platanus-hack-project.jsonc`, `project-description.md` y `project-logo.png` son lo que revisa Platanus. Solo se tocan cuando alguien del equipo lo pide.
