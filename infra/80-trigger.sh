#!/usr/bin/env bash
# Dos triggers de Cloud Build (web y api): push a main -> su cloudbuild.*.yaml, filtrados por ruta
# para que solo se reconstruya lo que cambió (docs y archivos de la entrega no disparan nada).
# La fuente es el espejo Pleo2/usaprais.com (el repo de la org no admite la GitHub App); `pnpm sync`
# le copia main después de cada merge.
# Requiere la conexión de GitHub ya autorizada (github-conn, una sola vez en la consola) y el backend
# desplegado: el trigger de la web lleva su URL (_API_URL), que Next fija al construir.
#   ./infra/80-trigger.sh            (GH_OWNER=Pleo2 GH_REPO=usaprais.com por defecto)
# Si un trigger ya existe se borra y se recrea, así los filtros siempre quedan al día.
source "$(dirname "$0")/config.sh"
require_gcloud

GH_OWNER="${GH_OWNER:-Pleo2}"
GH_REPO="${GH_REPO:-usaprais.com}"
CONNECTION="${CONNECTION:-github-conn}"
BRANCH="${BRANCH:-main}"
# El ID del recurso solo admite minúsculas, números y guiones (ej. Pleo2/usaprais.com -> pleo2-usaprais-com).
REPO_NAME="$(printf '%s-%s' "$GH_OWNER" "$GH_REPO" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n-' '-')"
REPO_RES="projects/${PROJECT_ID}/locations/${REGION}/connections/${CONNECTION}/repositories/${REPO_NAME}"

API_URL="$(service_url "$API_SERVICE" 2>/dev/null || true)"
[[ -n "$API_URL" ]] || { echo "${API_SERVICE} no existe todavía: corre 50-deploy-api.sh antes (la web necesita su URL)" >&2; exit 1; }

log "Repositorio enlazado: ${GH_OWNER}/${GH_REPO}"
if gcloud builds repositories describe "$REPO_NAME" --connection="$CONNECTION" --region="$REGION" >/dev/null 2>&1; then
  ok "repo ya enlazado"
else
  gcloud builds repositories create "$REPO_NAME" --connection="$CONNECTION" --region="$REGION" \
    --remote-uri="https://github.com/${GH_OWNER}/${GH_REPO}.git"
fi

ensure_trigger() {  # ensure_trigger <nombre> <cloudbuild.yaml> <archivos> <sustituciones>
  local name="$1" config="$2" files="$3" subs="$4"
  log "Trigger ${name}"
  if gcloud builds triggers describe "$name" --region="$REGION" >/dev/null 2>&1; then
    gcloud builds triggers delete "$name" --region="$REGION" --quiet
    ok "trigger anterior borrado"
  fi
  gcloud builds triggers create github \
    --name="$name" --region="$REGION" \
    --repository="$REPO_RES" \
    --branch-pattern="^${BRANCH}\$" \
    --build-config="$config" \
    --included-files="$files" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
    --substitutions="$subs"
  ok "trigger creado"
}

ensure_trigger "${API_SERVICE}-deploy" cloudbuild.api.yaml \
  'apps/api/**,cloudbuild.api.yaml' \
  "_REGION=${REGION},_REPO=${REPO},_SERVICE=${API_SERVICE}"

ensure_trigger "${WEB_SERVICE}-deploy" cloudbuild.web.yaml \
  'apps/web/**,pnpm-lock.yaml,pnpm-workspace.yaml,package.json,cloudbuild.web.yaml' \
  "_REGION=${REGION},_REPO=${REPO},_SERVICE=${WEB_SERVICE},_API_URL=${API_URL}"
