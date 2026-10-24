#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"
require_gcloud

log "Artifact Registry: ${REPO}"
if gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1; then
  ok "repo ya existe"
else
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location="$REGION" \
    --description="Imágenes de ${SERVICE}"
  ok "repo creado"
fi

# Las imágenes pesan cientos de MB y la capa gratuita de almacenamiento es chica:
# conserva las 5 más recientes y borra lo que tenga más de 30 días.
log "Política de limpieza"
POLICY="$(mktemp)"
cat >"$POLICY" <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}},
  {"name": "delete-old",  "action": {"type": "Delete"}, "condition": {"olderThan": "2592000s", "tagState": "any"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$REPO" \
  --location="$REGION" --policy="$POLICY" --no-dry-run
rm -f "$POLICY"
ok "limpieza configurada"
