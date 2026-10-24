#!/usr/bin/env bash
# Setup único del deploy en GCP. Lo corre una persona con gcloud y permisos de owner.
# Uso: bash deploy/setup-gcp.sh <project-id> [region]
set -euo pipefail

PROJECT_ID="${1:?uso: bash deploy/setup-gcp.sh <project-id> [region]}"
REGION="${2:-us-east1}"
SA="prais-deployer@$PROJECT_ID.iam.gserviceaccount.com"
HERE="$(cd "$(dirname "$0")" && pwd)"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe prais --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create prais --repository-format docker --location "$REGION"

# Cuenta que corre el build y despliega.
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create prais-deployer --display-name "Prais deploy"
for role in roles/cloudbuild.builds.editor roles/run.admin roles/iam.serviceAccountUser \
  roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA" --role "$role" --condition None --quiet >/dev/null
done

# Cuenta con la que corre Cloud Run: necesita usar Gemini en Vertex AI.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role roles/aiplatform.user --condition None --quiet >/dev/null

# Cada 5 minutos, Cloud Scheduler lanza el build de deploy/scheduler-build.json.
body="$(sed -e "s/__PROJECT_ID__/$PROJECT_ID/g" -e "s/__REGION__/$REGION/g" "$HERE/scheduler-build.json")"
gcloud scheduler jobs describe prais-deploy --location "$REGION" >/dev/null 2>&1 &&
  gcloud scheduler jobs delete prais-deploy --location "$REGION" --quiet
gcloud scheduler jobs create http prais-deploy --location "$REGION" --schedule "*/5 * * * *" \
  --uri "https://cloudbuild.googleapis.com/v1/projects/$PROJECT_ID/builds" --http-method POST \
  --headers Content-Type=application/json --message-body "$body" \
  --oauth-service-account-email "$SA"

echo "Listo. Para desplegar ya, sin esperar 5 minutos:"
echo "  gcloud scheduler jobs run prais-deploy --location $REGION"
