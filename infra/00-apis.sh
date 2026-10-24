#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"
require_gcloud

log "Habilitando APIs (idempotente)"
gcloud services enable "${APIS[@]}"
ok "APIs habilitadas"
