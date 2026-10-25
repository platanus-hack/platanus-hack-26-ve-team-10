#!/usr/bin/env bash
# Configuración única de la infra. Los demás scripts hacen `source` de este archivo.
# Cualquier variable se puede sobreescribir desde el entorno: REGION=us-central1 ./infra/up.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-prais-app}"

# OJO: la región de Firestore NO se puede cambiar después de crearla.
REGION="${REGION:-us-east1}"

REPO="${REPO:-prais}"                              # Artifact Registry
WEB_SERVICE="${WEB_SERVICE:-prais-web}"            # Next.js (público), reenvía /api/* al backend
API_SERVICE="${API_SERVICE:-prais-api}"            # Python/FastAPI (público: la web y Kapso le pegan directo)
WEB_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${WEB_SERVICE}"
API_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${API_SERVICE}"

# Identidades: una por servicio, con permisos mínimos
WEB_SA_NAME="${WEB_SA_NAME:-prais-web-run}"
API_SA_NAME="${API_SA_NAME:-prais-api-run}"
BUILD_SA_NAME="${BUILD_SA_NAME:-prais-build}"
WEB_SA="${WEB_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
API_SA="${API_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="${BUILD_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Dominio que apunta a prais-web (vacío = se omite 60-domain.sh). DNS en Cloudflare: "DNS only".
DOMAIN="${DOMAIN:-usaprais.com}"

# Cloud Run
PUBLIC="${PUBLIC:-true}"                           # true = web con --allow-unauthenticated (la API siempre es pública)
WEB_MAX_INSTANCES="${WEB_MAX_INSTANCES:-2}"        # tope de costo
API_MAX_INSTANCES="${API_MAX_INSTANCES:-4}"        # las sesiones están en Postgres, así que varias copias comparten la conversación
MIN_INSTANCES="${MIN_INSTANCES:-0}"                # >0 cuesta de forma continua. Para la demo: MIN_INSTANCES=1
API_MEMORY="${API_MEMORY:-2Gi}"                    # un turno baja fotos y varios caben a la vez: con 1Gi la instancia moría por OOM
API_CONCURRENCY="${API_CONCURRENCY:-8}"            # el default de 80 sobre 1 CPU era lo que llenaba la memoria
WEB_MEMORY="${WEB_MEMORY:-512Mi}"

# Vertex AI (Gemini): el backend usa la cuenta de servicio, sin API key.
# Los Gemini vigentes solo están en "global" (en us-east1 no hay 3.x) y el alias -latest no existe en Vertex.
VERTEX_LOCATION="${VERTEX_LOCATION:-global}"
PRAIS_MODEL="${PRAIS_MODEL:-gemini-3.8-flash}"

# Cola de Cloud Tasks de los mensajes de WhatsApp: el webhook encola y la cola llama a la API
# (/internal/whatsapp-task) con reintentos. TASKS_MAX_ATTEMPTS debe coincidir con la cola.
TASKS_QUEUE="${TASKS_QUEUE:-prais-jobs}"
TASKS_MAX_ATTEMPTS="${TASKS_MAX_ATTEMPTS:-5}"
TASKS_MAX_CONCURRENT="${TASKS_MAX_CONCURRENT:-20}"          # turnos del agente a la vez
TASKS_MAX_DISPATCHES="${TASKS_MAX_DISPATCHES:-20}"          # cuántos arranca por segundo

# Secretos: UN secreto JSON para el backend, montado como UNA variable de entorno APP_SECRETS
# (la app lo carga a variables de entorno al arrancar). La web no tiene secretos.
# Las claves vacías se omiten al crearlo; 40-secrets.sh las pide por prompt.
API_SECRET="${API_SECRET:-prais-api-secrets}"
API_SECRET_KEYS=(KAPSO_API_KEY KAPSO_WEBHOOK_SECRET FIRECRAWL_API_KEY APIFY_TOKEN SESSION_DATABASE_URL)

# Bucket de archivos (subidas, reportes, imágenes). Privado: el acceso es por IAM, nunca público.
BUCKET="${BUCKET:-${PROJECT_ID}-files}"

# Postgres de las sesiones del agente (infra/33-postgres.sh). La URL entra al secreto como
# SESSION_DATABASE_URL. Parar la instancia cuando no hay demo: activation-policy=never.
SQL_INSTANCE="${SQL_INSTANCE:-prais-pg}"
SQL_DATABASE="${SQL_DATABASE:-prais}"
SQL_USER="${SQL_USER:-prais}"

# Presupuesto (solo avisa, no corta el gasto)
BUDGET_USD="${BUDGET_USD:-10}"

# Firestore: colección y campo para TTL de datos efímeros (cachés)
TTL_COLLECTION="${TTL_COLLECTION:-cache}"
TTL_FIELD="${TTL_FIELD:-expireAt}"

APIS=(
  run.googleapis.com
  firestore.googleapis.com
  artifactregistry.googleapis.com
  cloudbuild.googleapis.com
  aiplatform.googleapis.com
  cloudtasks.googleapis.com
  secretmanager.googleapis.com
  sqladmin.googleapis.com
  iam.googleapis.com
  cloudresourcemanager.googleapis.com
  billingbudgets.googleapis.com
)

# --- helpers ---
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()  { printf '    \033[32m✓\033[0m %s\n' "$*"; }

require_gcloud() {
  command -v gcloud >/dev/null || { echo "gcloud no está instalado" >&2; exit 1; }
  local acct
  acct="$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
  [[ -n "$acct" ]] || { echo "Sin sesión. Corre: gcloud auth login" >&2; exit 1; }
  gcloud config set project "$PROJECT_ID" >/dev/null 2>&1
  ok "cuenta: $acct · proyecto: $PROJECT_ID · región: $REGION"
}

# secret_arg <secreto> -> "APP_SECRETS=<secreto>:latest" (formato de --set-secrets).
# Vacío, con aviso, si el secreto aún no existe (40-secrets.sh no crea secretos sin claves).
secret_arg() {
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    echo "APP_SECRETS=${1}:latest"
  else
    echo "    aviso: el secreto $1 no existe, se omite APP_SECRETS (corre 40-secrets.sh)" >&2
  fi
}

# build_image <dockerfile> <contexto> <imagen> [api_url]  -> deja la imagen en $BUILT_IMAGE
# Rutas relativas a la raíz del repo. Se construye en Cloud Build con infra/cloudbuild-image.yaml,
# así la web (contexto = raíz, workspace de pnpm) y la API usan el mismo mecanismo.
# api_url solo aplica a la web: Next lo lee al construir (rewrite de /api/*).
build_image() {
  local dockerfile="$1" context="$2" image="$3" api_url="${4:-}" tag
  [[ -f "$ROOT/$dockerfile" ]] || { echo "Falta $ROOT/$dockerfile" >&2; exit 1; }
  tag="${TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
  gcloud builds submit "$ROOT" --config="$ROOT/infra/cloudbuild-image.yaml" \
    --substitutions="_DOCKERFILE=${dockerfile},_CONTEXT=${context},_IMAGE=${image},_TAG=${tag},_API_URL=${api_url}"
  BUILT_IMAGE="${image}:${tag}"
}

# URL estable del servicio (con el número del proyecto): se conoce antes de desplegarlo. La API la usa
# como destino de sus tareas y como audiencia del token OIDC.
self_url() { echo "https://$1-$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)').${REGION}.run.app"; }

service_url() { gcloud run services describe "$1" --region="$REGION" --format='value(status.url)'; }
