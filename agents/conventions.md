# Convenciones

## Idioma

- Docs, interfaz y mensajes al usuario: en español de Venezuela.
- Código, identificadores, commits y títulos de PR: en inglés. Los commits siguen [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `ci:`.

## Ramas y PRs

1. Crea la rama desde `main` actualizado, con el nombre `<tipo>/<tema-corto>`. Por ejemplo, `feat/whatsapp-webhook`.
2. Abre el PR a `main` del repo de la org. `.github/workflows/auto-merge.yml` lo mergea solo, con merge commit y sin squash, para que se conserven los commits y autores de cada uno.
3. Si el PR no está listo, ábrelo como borrador: los borradores no se mergean.
4. Todavía no hay checks antes del merge. Corre `pnpm build && pnpm typecheck && pnpm lint` antes de abrir el PR.

## Mirror a prais.com

Cloud Build despliega desde `Pleo2/prais.com`, y `.github/workflows/sync-from-org.yml` lo pone al día cada 5 minutos con `main` de la org. Para que eso funcione:

- Nunca hagas commits directos en `prais.com`. Si tiene commits que no están en la org, el sync se detiene.
- Configura tu clon con las dos URLs de push, como explica el `README.md`.
- Si cambias algo en `.github/workflows/`, el sync no puede copiarlo, porque GitHub no deja que el token de Actions suba workflows. Después del merge, alguien con el mirror tiene que correr `git pull && git push origin main`.
- Para publicar sin esperar los 5 minutos, corre el workflow a mano: `gh workflow run sync-from-org.yml -R Pleo2/prais.com`.

## Código

- TypeScript en modo `strict` y módulos ESM.
- Cada paquete se llama `@prais/<nombre>`. Las dependencias internas van con `workspace:*`.
- Toda entrada externa se valida con zod: webhooks, query params, argumentos de tools y respuestas de las fuentes. Usa **zod 4** en todo el repo, la misma versión de la que depende `@google/adk`.
- Cada app guarda sus secretos en `.env`, que nunca se sube, y documenta las variables en `.env.example`. En GCP, los secretos van en Secret Manager.
- Fija versiones exactas de `@google/adk` y de los SDKs de las fuentes: cambian rápido.
- Cada app escucha en `process.env.PORT`, porque Cloud Run lo asigna.

## Docs

- `agents/`: cómo se construye cada parte. Lo leen las personas y los agentes de código.
- `docs/`: producto y decisiones. Cada decisión con matices va en `docs/decisions/NNNN-titulo.md`.
- `resources/`: material de referencia, no instrucciones.
- Si un cambio contradice un doc de `agents/`, actualiza el doc en el mismo PR.

## Archivos de la entrega

`README.md`, `platanus-hack-project.jsonc`, `project-description.md` y `project-logo.png` son lo que revisa Platanus. Solo se tocan cuando alguien del equipo lo pide.
