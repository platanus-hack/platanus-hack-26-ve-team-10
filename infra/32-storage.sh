#!/usr/bin/env bash
# Bucket de Cloud Storage para archivos de la app. Privado (acceso uniforme por IAM, sin acceso
# público); solo la SA de la API puede leer y escribir objetos.
source "$(dirname "$0")/config.sh"
require_gcloud

log "Bucket gs://${BUCKET}"
if gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  ok "bucket ya existe"
else
  gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
  ok "bucket creado en ${REGION}"
fi

log "La SA de la API puede leer y escribir objetos"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${API_SA}" --role=roles/storage.objectUser >/dev/null
ok "storage.objectUser → ${API_SA}"
