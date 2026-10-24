# Deploy en Google Cloud

Un solo servicio de Cloud Run (`prais`) con el `Dockerfile` de la raíz. El deploy lo hace Cloud Build, no GitHub Actions.

## Cómo llega un cambio a prod

1. El PR se mergea solo en `main` del repo de la org.
2. Cada 5 minutos, Cloud Scheduler lanza un build de Cloud Build (`deploy/scheduler-build.json`) que clona el repo de la org. Es público, así que no hace falta token ni conectar GitHub.
3. `deploy/step.sh check` compara `main` con el commit desplegado, que queda como label `commit` del servicio:
   - si es el mismo, o si solo cambiaron docs (`agents/`, `docs/`, `resources/`, `design/`, `.claude/`, `.github/`, archivos `.md` de la raíz y los archivos de la entrega), termina sin construir;
   - si cambió la app, sigue.
4. `build` construye la imagen y la sube a Artifact Registry (`<region>-docker.pkg.dev/<proyecto>/prais/web:<commit>`).
5. `deploy` la publica en Cloud Run. Si el servicio ya existe, solo cambia la imagen: las variables y los secretos se mantienen.

Un cambio tarda en publicarse hasta 5 minutos más lo que dure el build. Para no esperar:

```bash
gcloud scheduler jobs run prais-deploy --location us-east1
```

Los logs de cada build están en Cloud Build › Historial.

## Setup (una sola vez)

Lo corre alguien con `gcloud` y permisos de owner en el proyecto:

```bash
bash deploy/setup-gcp.sh <project-id> us-east1
```

El script:
- activa las APIs;
- crea el repositorio de imágenes;
- crea la cuenta `prais-deployer` con sus permisos;
- le da a Cloud Run acceso a Vertex AI;
- crea el job de Cloud Scheduler.

Si cambias `deploy/scheduler-build.json`, vuelve a correrlo para actualizar el job.

El primer deploy crea el servicio con estos ajustes:
- acceso público;
- `--no-cpu-throttling`, necesario para el `after()` del webhook de WhatsApp;
- un máximo de 2 instancias;
- Gemini en Vertex AI.

Los secretos de Kapso se agregan después, cuando existan:

```bash
gcloud run services update prais --region us-east1 \
  --set-secrets KAPSO_API_KEY=kapso-api-key:latest,KAPSO_WEBHOOK_SECRET=kapso-webhook-secret:latest
```

## Dominio

El DNS de usaprais.com está en Cloudflare. Agrega el dominio en Cloud Run ("Administrar dominios personalizados") y crea en Cloudflare el registro que te pida, en modo "DNS only" (nube gris), para que Google pueda emitir el certificado. Si la región no soporta dominios personalizados, usa `us-central1`.

## Costos

- Cada 5 minutos corre un build corto que normalmente termina en segundos sin construir. Cloud Build tiene una capa gratis y después cobra por minuto de build.
- Pon una alerta de presupuesto en el proyecto el primer día.
