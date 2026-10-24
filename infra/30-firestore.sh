#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"
require_gcloud

log "Firestore (default) en ${REGION}"
if gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  ok "base ya existe (la región no se puede cambiar)"
else
  echo "    ATENCIÓN: la región '${REGION}' es permanente."
  read -r -p "    ¿Crear la base en ${REGION}? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || { echo "cancelado"; exit 1; }
  gcloud firestore databases create --database='(default)' \
    --location="$REGION" --type=firestore-native
  ok "base creada"
fi

log "TTL en ${TTL_COLLECTION}.${TTL_FIELD}"
if gcloud firestore fields ttls update "$TTL_FIELD" \
     --collection-group="$TTL_COLLECTION" --enable-ttl --async >/dev/null 2>&1; then
  ok "TTL activado: los documentos con ${TTL_FIELD} vencido se borran solos"
else
  echo "    (TTL no se pudo activar ahora; reintenta cuando exista la colección)"
fi
