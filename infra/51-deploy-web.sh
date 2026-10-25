#!/usr/bin/env bash
# Build + deploy de prais-web (services/web, Next.js) a Cloud Run. Despliega la API antes: su URL se
# fija al CONSTRUIR la web (rewrite de /api/*), no al arrancarla. Si cambia la URL de la API,
# hay que reconstruir la web.
source "$(dirname "$0")/config.sh"
require_gcloud

API_URL="$(service_url "$API_SERVICE" 2>/dev/null || true)"
[[ -n "$API_URL" ]] || { echo "${API_SERVICE} no existe todavía: corre 50-deploy-api.sh" >&2; exit 1; }

log "Build ${WEB_IMAGE} (API_URL=${API_URL})"
build_image services/web/Dockerfile . "$WEB_IMAGE" "$API_URL"

AUTH_FLAG="--no-allow-unauthenticated"
[[ "$PUBLIC" == "true" ]] && AUTH_FLAG="--allow-unauthenticated"

# La web no tiene secretos ni variables de runtime: se limpian los de revisiones anteriores.
log "Deploy ${WEB_SERVICE} en ${REGION}"
gcloud run deploy "$WEB_SERVICE" \
  --image="$BUILT_IMAGE" \
  --region="$REGION" \
  --service-account="$WEB_SA" \
  --clear-env-vars \
  --clear-secrets \
  --min-instances="$MIN_INSTANCES" \
  --max-instances="$WEB_MAX_INSTANCES" \
  --memory="$WEB_MEMORY" \
  --port=8080 \
  "$AUTH_FLAG"

ok "URL: $(service_url "$WEB_SERVICE")"
