#!/usr/bin/env bash
# Un secreto JSON para el backend (ver API_SECRET en config.sh); la web no tiene secretos. Cada clave se pide por
# prompt (sin eco), se mezcla con el JSON de la versión actual para no pisar las demás y se escribe
# como versión nueva. Los valores nunca pasan por argumentos ni se imprimen.
# Claves vacías se omiten; un secreto sin ninguna clave no se crea.
# Migración: si una clave no está en el JSON pero existe un secreto suelto con su nombre
# (esquema anterior), se copia de ahí en vez de pedirla.
# Para rotar claves existentes: ./infra/40-secrets.sh --rotate
source "$(dirname "$0")/config.sh"
require_gcloud

command -v jq >/dev/null || { echo "jq no está instalado (brew install jq)" >&2; exit 1; }

ROTATE=false
[[ "${1:-}" == "--rotate" ]] && ROTATE=true

json_has() { printf '%s' "$1" | jq -e --arg k "$2" 'has($k)' >/dev/null 2>&1; }

# json_set <json> <clave> <valor>: el valor viaja por stdin, no por argumentos.
json_set() {
  printf '%s\n%s\n%s' "$1" "$2" "$3" |
    jq -Rsc 'split("\n") as $l | ($l[0] | fromjson) + {($l[1]): ($l[2:] | join("\n"))}'
}

# ensure_json_secret <secreto> <sa-con-acceso> <clave>...
ensure_json_secret() {
  local secret="$1" sa="$2" cur="{}" exists=false changed=false k v
  shift 2

  if gcloud secrets describe "$secret" >/dev/null 2>&1; then
    exists=true
    cur="$(gcloud secrets versions access latest --secret="$secret" 2>/dev/null || echo '{}')"
  fi

  for k in "$@"; do
    if json_has "$cur" "$k" && ! $ROTATE; then
      ok "$k ya está en $secret"
      continue
    fi
    v=""
    if ! json_has "$cur" "$k"; then
      v="$(gcloud secrets versions access latest --secret="$k" 2>/dev/null || true)"
      if [[ -n "$v" ]]; then ok "$k migrado desde el secreto suelto"; fi
    fi
    if [[ -z "$v" ]]; then
      read -r -s -p "    Valor de ${k} (vacío = omitir): " v || true
      echo
    fi
    if [[ -z "$v" ]]; then
      echo "    vacío, se omite $k"
      continue
    fi
    cur="$(json_set "$cur" "$k" "$v")"
    changed=true
    ok "$k listo"
  done
  v=""

  if [[ "$cur" == "{}" ]]; then
    echo "    $secret sin claves: no se crea"
    return 0
  fi

  $exists || gcloud secrets create "$secret" --replication-policy=automatic >/dev/null
  if $changed || ! $exists; then
    printf '%s' "$cur" | gcloud secrets versions add "$secret" --data-file=- >/dev/null
    ok "$secret: versión nueva ($(printf '%s' "$cur" | jq -r 'keys | length') claves)"
  fi
  cur=""

  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${sa}" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
  ok "$secret: acceso solo para $sa"
}

log "Secreto de ${API_SERVICE}: ${API_SECRET}"
ensure_json_secret "$API_SECRET" "$API_SA" "${API_SECRET_KEYS[@]}"
