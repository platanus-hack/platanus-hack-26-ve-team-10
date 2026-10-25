#!/usr/bin/env bash
# Corre todo en orden. Cada paso es idempotente, así que se puede repetir.
# 80-trigger y 90-cleanup-placeholder no van aquí: piden variables o confirmación propias.
set -euo pipefail
cd "$(dirname "$0")"

for step in 00-apis 10-registry 20-iam 30-firestore 32-storage 33-postgres 35-tasks 40-secrets \
            50-deploy-api 51-deploy-web 60-domain 70-budget; do
  if [[ -n "${SKIP:-}" && " $SKIP " == *" $step "* ]]; then
    echo "-- omitido $step"; continue
  fi
  ./"$step".sh
done
