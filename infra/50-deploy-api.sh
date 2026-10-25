#!/usr/bin/env bash
# Build + deploy de prais-api (services/api, Python/FastAPI) a Cloud Run. Público: la web (rewrite de
# /api/*) y el webhook de Kapso le pegan directo; el webhook se protege con su firma HMAC en la app.
# Despliega este servicio ANTES que la web: la web necesita su URL al construirse.
source "$(dirname "$0")/config.sh"
require_gcloud

log "Build ${API_IMAGE}"
build_image services/api/Dockerfile services/api "$API_IMAGE"

SECRET_ARG="$(secret_arg "$API_SECRET")"
SECRET_FLAG=()
[[ -n "$SECRET_ARG" ]] && SECRET_FLAG=(--set-secrets="$SECRET_ARG")

ENV_VARS="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION},PRAIS_MODEL=${PRAIS_MODEL}"
ENV_VARS+=",TASKS_QUEUE=${TASKS_QUEUE},TASKS_LOCATION=${REGION},TASKS_MAX_ATTEMPTS=${TASKS_MAX_ATTEMPTS}"
ENV_VARS+=",STORAGE_BUCKET=${BUCKET}"
ENV_VARS+=",TASKS_OIDC_SA=${API_SA},SELF_URL=$(self_url "$API_SERVICE")"

# El socket de Cloud SQL solo se monta si la instancia existe. Sin ella el proceso
# arranca igual y, si no hay SESSION_DATABASE_URL, las sesiones quedan en memoria.
CLOUD_SQL=()
if gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  CLOUD_SQL=(--add-cloudsql-instances="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')")
  ok "Cloud SQL: ${CLOUD_SQL[0]#--add-cloudsql-instances=}"
else
  echo "    aviso: no existe ${SQL_INSTANCE}. Corre 33-postgres.sh para que las sesiones sobrevivan un reinicio." >&2
fi

# --no-cpu-throttling: el webhook responde 200 y sigue trabajando; sin CPU asignada se cortaría.
log "Deploy ${API_SERVICE} en ${REGION}"
gcloud run deploy "$API_SERVICE" \
  --image="$BUILT_IMAGE" \
  --region="$REGION" \
  --service-account="$API_SA" \
  ${SECRET_FLAG[@]+"${SECRET_FLAG[@]}"} \
  ${CLOUD_SQL[@]+"${CLOUD_SQL[@]}"} \
  --set-env-vars="$ENV_VARS" \
  --min-instances="$MIN_INSTANCES" \
  --max-instances="$API_MAX_INSTANCES" \
  --memory="$API_MEMORY" \
  --concurrency="$API_CONCURRENCY" \
  --port=8080 \
  --no-cpu-throttling \
  --allow-unauthenticated

ok "URL: $(service_url "$API_SERVICE")"
