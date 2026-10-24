#!/usr/bin/env bash
# Alerta de presupuesto al 50%, 90% y 100%. Solo avisa; no corta el gasto.
source "$(dirname "$0")/config.sh"
require_gcloud

BILLING="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)' | sed 's#billingAccounts/##')"
[[ -n "$BILLING" ]] || { echo "El proyecto no tiene cuenta de facturación vinculada" >&2; exit 1; }

NAME="${REPO}-budget"
log "Presupuesto ${NAME} (${BUDGET_USD} USD) en cuenta ${BILLING}"
if gcloud billing budgets list --billing-account="$BILLING" --format='value(displayName)' | grep -qx "$NAME"; then
  ok "presupuesto ya existe"
else
  gcloud billing budgets create \
    --billing-account="$BILLING" \
    --display-name="$NAME" \
    --filter-projects="projects/${PROJECT_ID}" \
    --budget-amount="${BUDGET_USD}USD" \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0
  ok "presupuesto creado (los avisos llegan a los admins de la cuenta de facturación)"
fi
