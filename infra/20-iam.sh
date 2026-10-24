#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"
require_gcloud

ensure_sa() {
  local name="$1" email="$2" display="$3"
  if gcloud iam service-accounts describe "$email" >/dev/null 2>&1; then
    ok "SA ya existe: $email"
  else
    gcloud iam service-accounts create "$name" --display-name="$display"
    ok "SA creada: $email"
    sleep 10   # propagación de IAM
  fi
}

bind() {  # bind <sa-email> <role>
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" --role="$2" --condition=None --quiet >/dev/null
  ok "$2 → $1"
}

act_as() {  # act_as <sa-que-actúa> <sa-objetivo>
  gcloud iam service-accounts add-iam-policy-binding "$2" \
    --member="serviceAccount:$1" --role=roles/iam.serviceAccountUser --quiet >/dev/null
  ok "serviceAccountUser: $1 → $2"
}

log "Service accounts"
ensure_sa "$WEB_SA_NAME"   "$WEB_SA"   "Runtime de ${WEB_SERVICE}"
ensure_sa "$API_SA_NAME"   "$API_SA"   "Runtime de ${API_SERVICE}"
ensure_sa "$BUILD_SA_NAME" "$BUILD_SA" "Cloud Build de prais"

# El acceso al secreto se da en 40-secrets, a nivel de recurso. La SA de la web no lleva roles:
# solo sirve la interfaz y reenvía /api/* al backend.
log "Roles del runtime de la API"
bind "$API_SA" roles/datastore.user
bind "$API_SA" roles/aiplatform.user   # Gemini en Vertex AI

log "Roles de Cloud Build"
bind "$BUILD_SA" roles/run.admin
bind "$BUILD_SA" roles/artifactregistry.writer
bind "$BUILD_SA" roles/logging.logWriter
bind "$BUILD_SA" roles/storage.objectViewer

log "Cloud Build puede desplegar como cada runtime"
act_as "$BUILD_SA" "$WEB_SA"
act_as "$BUILD_SA" "$API_SA"

# Cloud Tasks firma el token OIDC con la SA de la API: quien encola (la propia API) debe poder actuar como ella.
log "La API puede encolar tareas firmadas con su propia identidad"
act_as "$API_SA" "$API_SA"
