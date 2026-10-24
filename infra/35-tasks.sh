#!/usr/bin/env bash
# Cola de Cloud Tasks de los mensajes de WhatsApp. El webhook (POST /whatsapp) encola un mensaje por tarea
# y la cola llama a /internal/whatsapp-task de la API con un token OIDC, reintentando si falla.
source "$(dirname "$0")/config.sh"
require_gcloud

QUEUE_FLAGS=(--max-attempts="$TASKS_MAX_ATTEMPTS" --min-backoff=10s --max-backoff=300s
             --max-dispatches-per-second=5 --max-concurrent-dispatches=5)

log "Cola ${TASKS_QUEUE}"
if gcloud tasks queues describe "$TASKS_QUEUE" --location="$REGION" >/dev/null 2>&1; then
  gcloud tasks queues update "$TASKS_QUEUE" --location="$REGION" "${QUEUE_FLAGS[@]}" >/dev/null
  ok "cola ya existe: configuración al día"
else
  gcloud tasks queues create "$TASKS_QUEUE" --location="$REGION" "${QUEUE_FLAGS[@]}"
  ok "cola creada"
fi

log "La SA de la API puede encolar"
gcloud tasks queues add-iam-policy-binding "$TASKS_QUEUE" --location="$REGION" \
  --member="serviceAccount:${API_SA}" --role=roles/cloudtasks.enqueuer --quiet >/dev/null
ok "cloudtasks.enqueuer → ${API_SA}"
