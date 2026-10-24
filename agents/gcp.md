# Deploy en Google Cloud

Un solo servicio de Cloud Run con el `Dockerfile` de la raíz.

## Primer deploy

```bash
gcloud run deploy prais --source . --region us-east1 --allow-unauthenticated \
  --no-cpu-throttling \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<proyecto>,GOOGLE_CLOUD_LOCATION=us-east1 \
  --set-secrets KAPSO_API_KEY=kapso-api-key:latest,KAPSO_WEBHOOK_SECRET=kapso-webhook-secret:latest
```

- `--no-cpu-throttling` hace falta para que el webhook de WhatsApp pueda responder después de devolver el 200 (usa `after()`).
- Los secretos se crean una vez en Secret Manager. La cuenta de servicio del servicio necesita el rol `Vertex AI User` y acceso a esos secretos.
- Con `max-instances` bajo se limita el gasto, y las sesiones en memoria se comparten mejor.

## Deploy continuo

En la consola de Cloud Run, usa "Configurar deploy continuo" con el repo **`Pleo2/prais.com`** y la rama `main`. No se puede conectar al repo de la org, porque no somos admins ahí. `prais.com` se pone al día solo cada 5 minutos ([conventions.md](conventions.md)).

## Dominio

El DNS de usaprais.com está en Cloudflare. Agrega el dominio en Cloud Run ("Administrar dominios personalizados") y crea en Cloudflare el registro que te pida, en modo "DNS only" (nube gris), para que Google pueda emitir el certificado. Si la región no soporta dominios personalizados, usa `us-central1`.

## Costos

Pon una alerta de presupuesto en el proyecto el primer día.
