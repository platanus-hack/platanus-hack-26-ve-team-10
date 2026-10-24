# Deploy en Google Cloud

Proyecto `prais-app`, región `us-east1`. Todo se crea con scripts de `gcloud` en [`infra/`](../infra/README.md) (idempotentes: se pueden repetir) y se despliega con Cloud Build. No usamos Terraform.

## Qué corre

| Servicio | Carpeta | Acceso | Notas |
|---|---|---|---|
| `prais-web` | `apps/web` | Público, en `usaprais.com` | Next.js con `output: "standalone"`. `API_URL` se fija al **construir**: es el destino del rewrite `/api/*` |
| `prais-api` | `apps/api` | Público | FastAPI. El webhook de Kapso se protege con su firma HMAC, no con IAM |

El backend se despliega antes que la web, porque la web necesita su URL para construirse. Si la URL del backend cambia, hay que reconstruir la web.

Configuración del backend:
- `--no-cpu-throttling`: la CPU queda asignada mientras la instancia vive. El webhook ya no depende de eso (encola y responde), pero cada turno del agente tarda varios segundos y así no se corta; sin cola, en local, el webhook sí lo necesita.
- `max-instances=1`: las sesiones del agente viven en memoria y varias instancias las perderían. `min-instances=0`, así que se apaga cuando no hay tráfico.
- Gemini en Vertex AI: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION`. La cuenta de servicio del backend tiene `Vertex AI User`, sin API key.
- Una cuenta de servicio por servicio, con permisos mínimos. La de la web no tiene roles ni secretos.
- Cola de WhatsApp (ver abajo): `TASKS_QUEUE`, `TASKS_LOCATION`, `TASKS_MAX_ATTEMPTS`, `TASKS_OIDC_SA` y `SELF_URL`. Las fija `infra/50-deploy-api.sh`.

## Cola de WhatsApp

Cola de Cloud Tasks `prais-jobs` (`infra/35-tasks.sh`): 5 intentos, espera de 10 a 300 s entre intentos y hasta 5 envíos por segundo. El webhook `POST /whatsapp` encola una tarea por mensaje de texto y la cola llama a `POST /internal/whatsapp-task` de `prais-api` con un token OIDC. Cómo funciona, en [kapso.md](kapso.md).

| Pieza | Detalle |
|---|---|
| `TASKS_QUEUE` / `TASKS_LOCATION` | Nombre de la cola y su región. Si `TASKS_QUEUE` no está, no se usa la cola (desarrollo local) |
| `TASKS_MAX_ATTEMPTS` | Debe coincidir con `--max-attempts` de la cola. En el último intento fallido se avisa a la persona |
| `TASKS_OIDC_SA` | `prais-api-run`: la cuenta que firma el token de cada tarea y la que la ruta interna espera |
| `SELF_URL` | URL estable del servicio (con el número del proyecto): destino de la tarea y audiencia del token |
| Permisos | `prais-api-run` es `cloudtasks.enqueuer` de la cola y puede actuar como sí misma (`serviceAccountUser`) para firmar el token (`infra/20-iam.sh`) |

## Almacenamiento

Bucket de Cloud Storage `prais-app-files` en `us-east1`, con acceso uniforme y sin acceso público. `prais-api-run` es `objectUser`, y el backend recibe el nombre en `STORAGE_BUCKET`. **El código todavía no lo usa.** Lo crea `infra/32-storage.sh`.

## Secretos

Un solo secreto JSON en Secret Manager, `prais-api-secrets`, montado en el backend como la variable `APP_SECRETS`. `app/config.py` lo vuelca al entorno al arrancar, así el código lee cada clave como variable normal. La web no tiene secretos.

| Clave | Para qué |
|---|---|
| `KAPSO_API_KEY` | Responder por WhatsApp |
| `KAPSO_WEBHOOK_SECRET` | Verificar la firma del webhook de Kapso |
| `FIRECRAWL_API_KEY` | Fuente de Firecrawl |
| `APIFY_TOKEN` | Fuentes de Apify |

`infra/40-secrets.sh` pide cada clave sin eco y la mezcla con la versión actual; las vacías se omiten. `--rotate` vuelve a pedir las existentes. Cloud Run lee el secreto al arrancar una instancia: tras rotar, redespliega con `infra/50-deploy-api.sh`.

## Dominio

`usaprais.com` (el apex, que es la `deploy-url` que valida Platanus) apunta a `prais-web` con un domain mapping (`infra/60-domain.sh`). En Cloudflare los registros son 4 `A` y 4 `AAAA` en el nombre `@` (los valores salen de `gcloud beta run domain-mappings describe --domain=usaprais.com --region=us-east1`), todos en modo **DNS only** (sin proxy), para que Google emita el certificado. El dominio está verificado en Search Console.

## CI/CD

Cloud Build, no GitHub Actions: los minutos de Actions son limitados, y el único workflow que queda es el auto-merge.

- **Fuente:** `main` del espejo `Pleo2/usaprais.com`. En el repo de la org no tenemos admin y no se puede instalar la GitHub App de Cloud Build. `pnpm sync` copia `main` al espejo después de cada merge.
- **Dos triggers**, `prais-web-deploy` y `prais-api-deploy`, sobre `main`, creados con `infra/80-trigger.sh`. Cada uno tiene filtro de rutas, así solo construye lo que cambió: la web con `apps/web/**`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` y el `package.json` de la raíz; la API con `apps/api/**`. Un cambio solo en docs (`agents/`, `docs/`, `resources/`, `design/`, `.claude/`, `.github/`, los `.md` de la raíz y los archivos de la entrega) no construye nada.
- **Pipelines:** [`cloudbuild.web.yaml`](../cloudbuild.web.yaml) y [`cloudbuild.api.yaml`](../cloudbuild.api.yaml). La API hace `ruff`, construye y despliega; la web construye (el build de Next ya revisa tipos) y despliega. El trigger de la web lleva la URL del backend (`_API_URL`).
- **El deploy de CI solo cambia la imagen.** Variables, secreto y flags se conservan de la revisión anterior, así que la primera vez hay que correr `infra/50-deploy-api.sh` y `infra/51-deploy-web.sh` a mano.

## Cómo llega un cambio a producción

1. PR a `main` del repo de la org y merge (se mergea solo).
2. `pnpm sync`: copia `main` al espejo.
3. El push dispara el trigger del servicio que cambió. El build aparece en Cloud Build → Historial.

**Forzar un deploy:**

```bash
gcloud builds triggers run prais-api-deploy --region=us-east1 --branch=main   # o prais-web-deploy
```

También sirve correr `infra/50-deploy-api.sh` o `infra/51-deploy-web.sh` desde tu máquina (construyen en Cloud Build con lo que tengas en el árbol de trabajo).

**Logs:** Cloud Run → el servicio → Logs, o

```bash
gcloud run services logs read prais-api --region=us-east1
```

## Costos

- Presupuesto de 10 USD con alertas al 50, 90 y 100 % (`infra/70-budget.sh`). Solo avisa: no corta el gasto.
- `--no-cpu-throttling` factura la CPU mientras la instancia está viva, no solo durante las peticiones. Con `min-instances=0` se apaga al quedar inactiva.
- Subir `min-instances` o `max-instances` cuesta más. Con `max-instances` mayor que 1 se pierden las sesiones del agente.
