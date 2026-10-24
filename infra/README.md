# infra

Scripts de `gcloud` para `prais-app`. Todo se configura en [config.sh](config.sh) y cada script es idempotente.
Los requisitos del equipo están en [agents/gcp.md](../agents/gcp.md).

Dos servicios de Cloud Run del monorepo:

| Servicio | Carpeta | Acceso | Identidad |
|---|---|---|---|
| `prais-web` (Next.js) | `apps/web` | público, `usaprais.com` | `prais-web-run` (sin roles ni secretos) |
| `prais-api` (Python/FastAPI) | `apps/api` | público; el webhook de Kapso se protege con su firma HMAC | `prais-api-run` |

La web reenvía `/api/*` al backend con un rewrite de Next. `API_URL` se lee al **construir** la web,
no al arrancarla, así que el backend se despliega antes y su URL entra como `--build-arg`; si esa URL
cambia, hay que reconstruir la web. Kapso apunta a `<url del backend>/whatsapp`.

```bash
gcloud auth login
./infra/00-apis.sh          # habilita APIs (incluye Vertex AI)
./infra/10-registry.sh      # Artifact Registry + limpieza
./infra/20-iam.sh           # service accounts y roles mínimos
./infra/30-firestore.sh     # Firestore Native + TTL (región permanente)
./infra/40-secrets.sh       # secreto JSON del backend (claves por prompt) y acceso para su SA
./infra/50-deploy-api.sh    # build + Cloud Run del backend (apps/api/Dockerfile)
./infra/51-deploy-web.sh    # build + Cloud Run de la web (apps/web/Dockerfile, contexto = raíz)
./infra/60-domain.sh        # domain mapping DOMAIN -> prais-web
./infra/70-budget.sh        # alertas de presupuesto
./infra/90-cleanup-placeholder.sh  # borra el servicio de prueba "prais" (con confirmación)
```

`./infra/up.sh` corre del 00 al 70; `SKIP="60-domain 70-budget" ./infra/up.sh` omite pasos.
Las imágenes se construyen en Cloud Build con [cloudbuild-image.yaml](cloudbuild-image.yaml).

## CI/CD

`cloudbuild.web.yaml` y `cloudbuild.api.yaml` en la raíz. `./infra/80-trigger.sh` enlaza el espejo
`Pleo2/usaprais.com` (la conexión `github-conn` ya autorizada) y crea un trigger por servicio sobre
`main`, con filtro de rutas: la web con `apps/web/**`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` y
`package.json`; la API con `apps/api/**`. Docs y archivos de la entrega no disparan builds.
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

`40-secrets.sh` pide cada clave (sin eco), la mezcla con la versión actual y escribe una versión nueva;
las vacías se omiten y un secreto sin claves no se crea. `--rotate` vuelve a pedir las existentes.
Cloud Run lee el secreto al arrancar una instancia: tras rotar, redespliega (50). Gemini va por Vertex AI
con la cuenta de servicio (`roles/aiplatform.user`), sin API key.

## Costos

- El backend usa `--no-cpu-throttling` (el webhook responde 200 y sigue trabajando): la CPU se factura
  mientras la instancia está viva, no solo durante las peticiones. Con `--min-instances=0` se apaga al
  quedar inactiva.
- `API_MAX_INSTANCES=1` por defecto: las sesiones del agente viven en memoria y varias instancias las perderían.
- `MIN_INSTANCES` mayor que 0 cuesta de forma continua; los presupuestos solo avisan.

Variables útiles: `REGION`, `VERTEX_LOCATION`, `DOMAIN`, `PUBLIC`, `WEB_MAX_INSTANCES`, `API_MAX_INSTANCES`, `BUDGET_USD`.
