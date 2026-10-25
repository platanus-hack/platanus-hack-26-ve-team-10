#!/usr/bin/env bash
# Arma services/api/.env para desarrollo, con las claves de fuentes que ya están en el
# secreto de producción. No entra en up.sh: no toca la nube, solo lee el secreto.
#
#   ./infra/env-local.sh              # Firecrawl, Apify, Vertex y sesiones en SQLite
#   CON_KAPSO=1 ./infra/env-local.sh  # además KAPSO_*, para probar el webhook con un túnel
#   FORCE=1 ./infra/env-local.sh      # sobrescribe un .env que ya existe
#
# Por defecto deja fuera dos cosas a propósito:
#   KAPSO_API_KEY        con ella, el código de WhatsApp manda mensajes de verdad desde
#                        el número de producción. Solo con CON_KAPSO=1 y a sabiendas.
#   SESSION_DATABASE_URL la de prod apunta a Cloud SQL por el socket de Cloud Run; en
#                        local no conecta, y si conectara escribirías las conversaciones
#                        reales. Aquí se usa SQLite.
source "$(dirname "$0")/config.sh"
require_gcloud

ADC="$HOME/.config/gcloud/application_default_credentials.json"
if [[ ! -f "$ADC" ]]; then
  echo
  echo "Faltan las credenciales de aplicación. Sin ellas el modelo no responde y el agente" >&2
  echo "contesta «Falló la búsqueda de ...», que no se parece en nada a la causa." >&2
  echo >&2
  if [[ -t 0 ]]; then
    read -r -p "¿Corro 'gcloud auth application-default login' ahora? [s/N] " yes
    [[ "$yes" =~ ^[sSyY]$ ]] && gcloud auth application-default login
  else
    echo "    gcloud auth application-default login" >&2
  fi
  echo
fi

ENV_FILE="$ROOT/services/api/.env"
if [[ -f "$ENV_FILE" && -z "${FORCE:-}" ]]; then
  echo "Ya existe $ENV_FILE. Repite con FORCE=1 delante para sobrescribirlo." >&2
  exit 1
fi

log "Leyendo $API_SECRET"
SECRET_JSON="$(gcloud secrets versions access latest --secret="$API_SECRET" --project="$PROJECT_ID")"

# Las claves salen del JSON por nombre: si una falta, queda vacía y el .env lo dice.
clave() { printf '%s' "$SECRET_JSON" | python3 -I -c "import json,sys; print(json.load(sys.stdin).get('$1',''))"; }

FIRECRAWL="$(clave FIRECRAWL_API_KEY)"
APIFY="$(clave APIFY_TOKEN)"

{
  echo "# Generado por infra/env-local.sh el $(date '+%Y-%m-%d %H:%M'). No se commitea."
  echo
  echo "# El modelo por Vertex, con tus credenciales de aplicación: no hace falta una API key."
  echo "# Si no las tienes: gcloud auth application-default login"
  echo "GOOGLE_GENAI_USE_VERTEXAI=true"
  echo "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  echo "GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION}"
  echo "PRAIS_MODEL=${PRAIS_MODEL}"
  echo
  echo "# Fuentes. Son las MISMAS claves que usa producción: tus pruebas comparten con el"
  echo "# bot en vivo los 5 runs concurrentes de Apify y el cupo de Firecrawl. Si ves"
  echo "# tiempos raros o RateLimitError, puede ser eso y no tu cambio."
  echo "FIRECRAWL_API_KEY=${FIRECRAWL}"
  echo "APIFY_TOKEN=${APIFY}"
  echo
  echo "# Sesiones en un archivo local: el hilo sobrevive a reiniciar el API."
  echo "SESSION_DATABASE_URL=sqlite+aiosqlite:///./.sessions.db"
  if [[ -n "${CON_KAPSO:-}" ]]; then
    echo
    echo "# CUIDADO: con estas claves se manda WhatsApp de verdad desde el número de producción."
    echo "KAPSO_API_KEY=$(clave KAPSO_API_KEY)"
    echo "KAPSO_WEBHOOK_SECRET=$(clave KAPSO_WEBHOOK_SECRET)"
  fi
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

[[ -n "$FIRECRAWL" ]] || echo "    aviso: FIRECRAWL_API_KEY vino vacía del secreto." >&2
[[ -n "$APIFY" ]] || echo "    aviso: APIFY_TOKEN vino vacío del secreto." >&2
ok "Escrito $ENV_FILE"

if [[ -f "$ADC" ]]; then
  ok "Credenciales de aplicación listas: Vertex debería responder"
else
  echo "    pendiente: gcloud auth application-default login" >&2
fi

echo
echo "Ahora: pnpm dev    (api en :4000, web en :3000)"
echo "El chat de la web, en http://localhost:3000/chat, llama al mismo agente que WhatsApp."
