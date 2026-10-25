# infra

Scripts de `gcloud` para `prais-app`. Todo se configura en [config.sh](config.sh) y cada script es idempotente.
Los requisitos del equipo están en [docs/gcp.md](../docs/gcp.md).

## Para desarrollar en local

[`env-local.sh`](env-local.sh) arma `services/api/.env` leyendo el secreto de producción. No entra en
`up.sh` porque no toca la nube: solo lee.

```bash
./infra/env-local.sh              # Firecrawl, Apify, Vertex y sesiones en SQLite
CON_KAPSO=1 ./infra/env-local.sh  # además KAPSO_*, para el webhook con un túnel
FORCE=1 ./infra/env-local.sh      # sobrescribe un .env que ya existe
```

Deja fuera dos cosas a propósito. `KAPSO_API_KEY`, porque con ella el código de WhatsApp manda
mensajes de verdad desde el número de producción. Y `SESSION_DATABASE_URL`, porque la de prod entra
por el socket de Cloud SQL: en local no conecta, y si conectara escribirías las conversaciones reales.

El modelo va por Vertex con tus propias credenciales, así que **hace falta
`gcloud auth application-default login`**. Sin eso el SDK lanza `DefaultCredentialsError`, el agente
lo atrapa y responde «Falló la búsqueda de …», que no se parece en nada a la causa. El script lo
avisa antes de escribir nada.

Las claves de fuentes son **las mismas que usa producción**: tus pruebas comparten con el bot en vivo
los 5 runs concurrentes de Apify y el cupo de Firecrawl.

Dos servicios de Cloud Run del monorepo:

| Servicio | Carpeta | Acceso | Identidad |
|---|---|---|---|
| `prais-web` (Next.js) | `services/web` | público, `usaprais.com` | `prais-web-run` (sin roles ni secretos) |
| `prais-api` (Python/FastAPI) | `services/api` | público; el webhook de Kapso se protege con su firma HMAC | `prais-api-run` |

La web reenvía `/api/*` al backend con un rewrite de Next. `API_URL` se lee al **construir** la web,
no al arrancarla, así que el backend se despliega antes y su URL entra como `--build-arg`; si esa URL
cambia, hay que reconstruir la web. Kapso apunta a `<url del backend>/whatsapp`.

```bash
gcloud auth login
./infra/00-apis.sh          # habilita APIs (incluye Vertex AI)
./infra/10-registry.sh      # Artifact Registry + limpieza
./infra/20-iam.sh           # service accounts y roles mínimos
./infra/30-firestore.sh     # Firestore Native + TTL (región permanente)
./infra/33-postgres.sh      # Cloud SQL: sesiones del agente (escribe SESSION_DATABASE_URL)
./infra/40-secrets.sh       # secreto JSON del backend (claves por prompt) y acceso para su SA
./infra/50-deploy-api.sh    # build + Cloud Run del backend (services/api/Dockerfile)
./infra/51-deploy-web.sh    # build + Cloud Run de la web (services/web/Dockerfile, contexto = raíz)
./infra/60-domain.sh        # domain mapping DOMAIN -> prais-web
./infra/70-budget.sh        # alertas de presupuesto
./infra/90-cleanup-placeholder.sh  # borra el servicio de prueba "prais" (con confirmación)
```

`./infra/up.sh` corre del 00 al 70; `SKIP="60-domain 70-budget" ./infra/up.sh` omite pasos.
Las imágenes se construyen en Cloud Build con [cloudbuild-image.yaml](cloudbuild-image.yaml).

## CI/CD

`cloudbuild.web.yaml` y `cloudbuild.api.yaml` en la raíz. `./infra/80-trigger.sh` enlaza el espejo
`Pleo2/usaprais.com` (la conexión `github-conn` ya autorizada) y crea un trigger por servicio sobre
`main`, con filtro de rutas: la web con `services/web/**`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` y
`package.json`; la API con `services/api/**`. Docs y archivos de la entrega no disparan builds.
Si un trigger ya existe, el script lo borra y lo recrea. El trigger de la web lleva `_API_URL`.
El deploy de CI solo cambia la imagen; variables, secreto y flags se conservan de los scripts 50 y 51.

Flujo: PR a `main` de la org, merge, `pnpm sync` copia `main` al espejo y el push dispara los triggers.

## Secretos

Un solo secreto JSON, `prais-api-secrets`, montado en el backend como `APP_SECRETS` (la app lo carga
a variables de entorno al arrancar). La web no tiene secretos.

| Clave | Para qué |
|---|---|
| `KAPSO_API_KEY` | responder por WhatsApp |
| `KAPSO_WEBHOOK_SECRET` | verificar la firma del webhook de Kapso |
| `FIRECRAWL_API_KEY` | fuente de Firecrawl |
| `APIFY_TOKEN` | fuentes de Apify |
| `SESSION_DATABASE_URL` | Postgres de las sesiones. La escribe `33-postgres.sh` |

`40-secrets.sh` pide cada clave (sin eco), la mezcla con la versión actual y escribe una versión nueva;
las vacías se omiten y un secreto sin claves no se crea. `--rotate` vuelve a pedir las existentes.
Cloud Run lee el secreto al arrancar una instancia: tras rotar, redespliega (50). Gemini va por Vertex AI
con la cuenta de servicio (`roles/aiplatform.user`), sin API key.

## Costos

- El backend usa `--no-cpu-throttling` (el webhook responde 200 y sigue trabajando): la CPU se factura
  mientras la instancia está viva, no solo durante las peticiones. Con `--min-instances=0` se apaga al
  quedar inactiva.
- `API_MAX_INSTANCES=4` y `API_MEMORY=1Gi`: las sesiones están en Postgres, así que varias copias comparten la conversación. La cola corre 20 turnos a la vez.
- `MIN_INSTANCES` mayor que 0 cuesta de forma continua. Para la demo: `MIN_INSTANCES=1 ./infra/50-deploy-api.sh`, y después volver a 0.
- `prais-pg` cobra mientras está encendida. Apagarla: `gcloud sql instances patch prais-pg --activation-policy=never`.

Variables útiles: `REGION`, `VERTEX_LOCATION`, `DOMAIN`, `PUBLIC`, `WEB_MAX_INSTANCES`, `API_MAX_INSTANCES`, `API_MEMORY`, `MIN_INSTANCES`, `BUDGET_USD`.
