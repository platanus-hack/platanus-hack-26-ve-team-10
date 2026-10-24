#!/usr/bin/env bash
# Pasos del build que Cloud Scheduler lanza cada 5 minutos (deploy/scheduler-build.json).
# check:  decide si hay que desplegar. Solo despliega si main cambió algo más que docs.
# build:  construye y sube la imagen.
# deploy: publica la imagen en Cloud Run y la marca con el commit.
# Corre en /workspace, con REGION y PROJECT_ID en el entorno y el repo clonado en ./repo.
set -euo pipefail

SERVICE=prais
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/prais/web"
# Cambios que no afectan la app: no disparan un deploy.
DOCS_ONLY='^(agents/|docs/|resources/|design/|\.claude/|\.github/|[^/]+\.md$|project-logo\.png$|platanus-hack-project\.jsonc$|\.gitignore$)'

case "$1" in
  check)
    commit="$(git -C repo rev-parse --short=12 HEAD)"
    deployed="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(metadata.labels.commit)' 2>/dev/null || true)"
    decision=yes
    if [[ "$deployed" == "$commit" ]]; then
      decision=no
    elif [[ -n "$deployed" ]] && git -C repo cat-file -e "$deployed^{commit}" 2>/dev/null; then
      changed="$(git -C repo diff --name-only "$deployed" "$commit" | grep -vE "$DOCS_ONLY" || true)"
      [[ -z "$changed" ]] && decision=no
    fi
    echo "$commit" > .commit
    echo "$decision" > .deploy
    echo "desplegado: ${deployed:-nada} · main: $commit · deploy: $decision"
    ;;
  build)
    [[ "$(cat .deploy)" == yes ]] || exit 0
    docker build -t "$IMAGE:$(cat .commit)" repo
    docker push "$IMAGE:$(cat .commit)"
    ;;
  deploy)
    [[ "$(cat .deploy)" == yes ]] || exit 0
    commit="$(cat .commit)"
    if gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1; then
      # Ya existe: solo cambia la imagen. Variables y secretos se mantienen.
      gcloud run deploy "$SERVICE" --region "$REGION" --image "$IMAGE:$commit" --update-labels "commit=$commit" --quiet
    else
      gcloud run deploy "$SERVICE" --region "$REGION" --image "$IMAGE:$commit" --labels "commit=$commit" \
        --allow-unauthenticated --no-cpu-throttling --max-instances 2 \
        --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global" \
        --quiet
    fi
    ;;
  *)
    echo "uso: step.sh check|build|deploy" >&2
    exit 1
    ;;
esac
