#!/usr/bin/env bash
# Domain mapping de DOMAIN -> prais-web (preview, gratis). Requiere el dominio verificado
# en Search Console con la misma cuenta de gcloud (propietario).
source "$(dirname "$0")/config.sh"
require_gcloud

if [[ -z "$DOMAIN" ]]; then
  echo "DOMAIN vacío en config.sh, se omite el mapeo"; exit 0
fi

log "Domain mapping ${DOMAIN} → ${WEB_SERVICE}"
current="$(gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" \
  --format='value(spec.routeName)' 2>/dev/null || true)"

if [[ "$current" == "$WEB_SERVICE" ]]; then
  ok "mapeo ya existe"
else
  if [[ -n "$current" ]]; then
    echo "    ${DOMAIN} apunta hoy a '${current}'. Para cambiarlo hay que borrar el mapeo y recrearlo."
    read -r -p "    ¿Borrar y recrear hacia ${WEB_SERVICE}? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || { echo "cancelado"; exit 1; }
    gcloud beta run domain-mappings delete --domain="$DOMAIN" --region="$REGION" --quiet
  fi
  gcloud beta run domain-mappings create \
    --service="$WEB_SERVICE" --domain="$DOMAIN" --region="$REGION"
  ok "mapeo creado"
fi

log "Registros DNS que debes crear en Cloudflare (proxy apagado)"
gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" \
  --format='table(status.resourceRecords.type,status.resourceRecords.name,status.resourceRecords.rrdata)'
echo "    El certificado TLS tarda de minutos a horas tras propagar el DNS."
