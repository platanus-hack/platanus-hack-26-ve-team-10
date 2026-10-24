#!/usr/bin/env bash
# Borra el servicio de prueba "prais" (imagen hello) que se desplegó antes de separar web y api.
# Correr DESPUÉS de 60-domain.sh, que mueve el dominio a prais-web.
source "$(dirname "$0")/config.sh"
require_gcloud

OLD="${OLD_SERVICE:-prais}"
log "Servicio de prueba '${OLD}'"
if ! gcloud run services describe "$OLD" --region="$REGION" >/dev/null 2>&1; then
  ok "no existe, nada que borrar"; exit 0
fi

read -r -p "    ¿Borrar el servicio '${OLD}' en ${REGION}? [y/N] " yn
[[ "$yn" =~ ^[Yy]$ ]] || { echo "cancelado"; exit 1; }
gcloud run services delete "$OLD" --region="$REGION" --quiet
ok "borrado"
