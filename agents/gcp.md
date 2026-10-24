# Infraestructura en Google Cloud

Todo corre en un proyecto de Google Cloud. Cloudflare solo maneja el DNS de usaprais.com.

## Servicios

| Pieza | Servicio de GCP | Notas |
|---|---|---|
| `apps/web`, `apps/agent`, `apps/whatsapp`, `apps/mcp` | Cloud Run (un servicio por app) | `min-instances=0` para no pagar en reposo. Ponle `max-instances` a cada servicio para limitar el gasto |
| `apps/ingest` | Cloud Run Jobs + Cloud Scheduler | Un job por fuente o por lote. Scheduler los dispara |
| Modelo | Vertex AI (Gemini) | En Cloud Run se autentica con la cuenta de servicio, sin API keys |
| Secretos | Secret Manager | Se montan como variables de entorno en Cloud Run |
| Trabajo asíncrono | Cloud Tasks | Por ejemplo, para procesar un mensaje de WhatsApp después de responderle 200 a Kapso |
| Índice | Firestore o Cloud SQL con Postgres | Decisión abierta |
| Evidencia | Cloud Storage | Respuesta cruda de cada fuente, para poder mostrar de dónde salió un precio |
| Logs y trazas | Cloud Logging y Cloud Trace | ADK trae exportadores de OpenTelemetry para GCP |
| Builds | Cloud Build + Artifact Registry | Un trigger por app |

Región sugerida: `us-east1`, por cercanía a Venezuela. Usa la misma región en todos los servicios.

## Deploy

1. Cloud Build se conecta a GitHub con su GitHub App, sobre **`Pleo2/prais.com`**. No se puede conectar al repo de la org: no somos admins ahí.
2. Hay un trigger por app sobre la rama `main`, con filtro de archivos incluidos. Por ejemplo, el de la web se dispara con `apps/web/**` y `packages/**`.
3. Cada app tiene un `Dockerfile`, y el contexto del build es la raíz del repo, porque las apps dependen de `packages/core`.
4. El trigger construye la imagen, la sube a Artifact Registry y la despliega en Cloud Run.

¿Por qué Cloud Build y no GitHub Actions en `prais.com`? `prais.com` se actualiza con un push hecho con el token de Actions, y esos pushes no disparan otros workflows de Actions. Los triggers de Cloud Build sí se disparan, porque escuchan los webhooks de su GitHub App.

## Builds en el monorepo

- Next.js se construye con `output: "standalone"`. El Dockerfile copia `.next/standalone`, `.next/static` y `public`.
- Para las apps de Node, `pnpm --filter @prais/<app> deploy --prod <dir>` arma una carpeta con solo las dependencias de esa app.
- Cada imagen escucha en `$PORT`, porque Cloud Run lo asigna.

## Dominio

El DNS de usaprais.com está en Cloudflare. Cada subdominio apunta a su servicio de Cloud Run con un domain mapping. Si la región no lo soporta, se pone un load balancer o Firebase Hosting delante.

- Crea los registros en Cloudflare en modo "DNS only" (nube gris), para que Google pueda emitir el certificado.
- Si después activan el proxy de Cloudflare, revisa [seo-geo.md](seo-geo.md): Cloudflare bloquea por defecto los crawlers de IA.

## Cuentas de servicio

Cada servicio tiene su propia cuenta de servicio, con solo los permisos que necesita:

- `agent`: Vertex AI y lectura del índice.
- `ingest`: escritura del índice, Cloud Storage y los secretos de las fuentes.
- `whatsapp`: Cloud Tasks y su secreto de Kapso.
- `web` y `mcp`: invocar al agente.

El agente no es público: solo lo invocan las otras apps con sus cuentas de servicio.

## Costos

- Pon una alerta de presupuesto en el proyecto el primer día.
- Las cuentas de Apify, Firecrawl y Gemini cobran por uso. Ponles límites en sus propios paneles.

## Por decidir

- **El índice: Firestore o Cloud SQL.** Firestore no necesita esquema y tiene capa gratis, así que es más rápido para la hackathon. Cloud SQL con Postgres es mejor para historial de precios y rankings, pero cuesta desde el primer minuto.
- **Quién crea el proyecto** y bajo qué cuenta de facturación (¿hay créditos de Google en la hackathon?).
