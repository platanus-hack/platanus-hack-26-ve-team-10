# Deploy en Google Cloud

> **Pendiente.** Lo arma el dev a cargo de GCP: crea sus propios archivos y la configuración. Cuando esté, reemplaza esta sección con cómo funciona de verdad.

## Lo que tiene que cumplir

- **Cloud Build, no GitHub Actions.** Los minutos de Actions son limitados. El único workflow que queda es el auto-merge, y corre en el repo de la org, que es público.
- **Construir por scope.** Solo construye y despliega si cambió la app. Si solo cambiaron docs (`agents/`, `docs/`, `resources/`, `design/`, `.claude/`, `.github/`, los `.md` de la raíz y los archivos de la entrega), no construye.
- **Fuente: `main` del repo de la org.** Es público, así que se puede clonar sin token. No tenemos admin ahí, así que no se puede instalar la GitHub App de Cloud Build en ese repo.
- **Dos servicios de Cloud Run:** `apps/api` (Fastify; `pnpm --filter @prais/api build` y `node dist/server.js`) y `apps/web` (Next.js con `output: "standalone"`). Los dos escuchan en `PORT`. Los Dockerfiles los crea el dev a cargo.
- **`API_URL` al construir la web.** Next fija el destino del rewrite `/api/*` en el build, así que la URL del backend tiene que estar en el entorno de `next build`.
- **`--no-cpu-throttling` en el backend**, porque el webhook de WhatsApp responde y sigue trabajando después del 200.
- **Gemini en Vertex AI**, con `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` y `GOOGLE_CLOUD_LOCATION`. La cuenta de Cloud Run necesita el rol `Vertex AI User`.
- **Secretos en Secret Manager:** `KAPSO_API_KEY` y `KAPSO_WEBHOOK_SECRET`.
- **Pocas instancias** (`max-instances` bajo), para limitar el gasto. Además, las sesiones del agente viven en memoria.
- **Dominio usaprais.com.** El DNS está en Cloudflare: los registros van en modo "DNS only" para que Google emita el certificado.
- **Alerta de presupuesto** desde el primer día.

Cuando el deploy exista, documenta aquí cómo llega un cambio a prod, cómo forzar un deploy y dónde ver los logs.
