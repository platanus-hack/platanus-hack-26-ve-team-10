#!/usr/bin/env bash
# Postgres de las sesiones del agente. La instancia queda con IP pública y sin redes
# autorizadas: nadie entra por esa IP. Cloud Run entra por el socket que monta
# --add-cloudsql-instances. La URL (con la clave) se escribe en el secreto del API
# y no se imprime. Si la clave ya está, no se rota.
#
# Parar cuando no haya demo (deja de cobrar el cómputo; el disco sigue):
#   gcloud sql instances patch prais-pg --activation-policy=never --project=prais-app
# Volver a encenderla:
#   gcloud sql instances patch prais-pg --activation-policy=always --project=prais-app
source "$(dirname "$0")/config.sh"
require_gcloud

command -v jq >/dev/null || { echo "jq no está instalado (brew install jq)" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 no está instalado" >&2; exit 1; }

log "API de Cloud SQL"
gcloud services enable sqladmin.googleapis.com >/dev/null
ok "sqladmin"

secret_url() {
  gcloud secrets describe "$API_SECRET" >/dev/null 2>&1 || return 1
  gcloud secrets versions access latest --secret="$API_SECRET" 2>/dev/null |
    jq -e --arg k SESSION_DATABASE_URL '.[$k] | type == "string" and length > 0' >/dev/null
}

log "Instancia ${SQL_INSTANCE}"
if gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  ok "instancia ya existe"
else
  root="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 \
    --edition=enterprise \
    --tier=db-g1-small \
    --region="$REGION" \
    --storage-size=10 \
    --storage-type=SSD \
    --availability-type=zonal \
    --backup-start-time=08:00 \
    --retained-backups-count=3 \
    --root-password="$root" >/dev/null
  root=""
  ok "instancia creada (enterprise, db-g1-small, disco de 10 GB)"
fi

if secret_url; then
  ok "SESSION_DATABASE_URL ya está en ${API_SECRET}; no se rota"
  exit 0
fi

log "Base ${SQL_DATABASE} y usuario ${SQL_USER}"
if gcloud sql databases describe "$SQL_DATABASE" --instance="$SQL_INSTANCE" >/dev/null 2>&1; then
  ok "base ya existe"
else
  gcloud sql databases create "$SQL_DATABASE" --instance="$SQL_INSTANCE" >/dev/null
  ok "base creada"
fi

app_pass="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
if gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$SQL_USER"; then
  gcloud sql users set-password "$SQL_USER" --instance="$SQL_INSTANCE" --password="$app_pass" >/dev/null
  ok "clave del usuario rotada"
else
  gcloud sql users create "$SQL_USER" --instance="$SQL_INSTANCE" --password="$app_pass" >/dev/null
  ok "usuario creado"
fi

conn="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
url="$(APP_PASS="$app_pass" SQL_USER="$SQL_USER" SQL_DATABASE="$SQL_DATABASE" CONN="$conn" python3 - <<'PY'
import os
import urllib.parse

user = urllib.parse.quote(os.environ["SQL_USER"], safe="")
password = urllib.parse.quote(os.environ["APP_PASS"], safe="")
database = urllib.parse.quote(os.environ["SQL_DATABASE"], safe="")
host = urllib.parse.quote("/cloudsql/" + os.environ["CONN"], safe="/:")
print(f"postgresql+asyncpg://{user}:{password}@/{database}?host={host}")
PY
)"
app_pass=""

cur="{}"
if gcloud secrets describe "$API_SECRET" >/dev/null 2>&1; then
  cur="$(gcloud secrets versions access latest --secret="$API_SECRET" 2>/dev/null || echo '{}')"
else
  gcloud secrets create "$API_SECRET" --replication-policy=automatic >/dev/null
fi
cur="$(printf '%s\n%s\n%s' "$cur" SESSION_DATABASE_URL "$url" |
  jq -Rsc 'split("\n") as $l | ($l[0] | fromjson) + {($l[1]): ($l[2:] | join("\n"))}')"
printf '%s' "$cur" | gcloud secrets versions add "$API_SECRET" --data-file=- >/dev/null
url=""
cur=""
gcloud secrets add-iam-policy-binding "$API_SECRET" \
  --member="serviceAccount:${API_SA}" --role=roles/secretmanager.secretAccessor --quiet >/dev/null
ok "SESSION_DATABASE_URL escrito en ${API_SECRET}"
