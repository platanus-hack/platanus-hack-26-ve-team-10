#!/usr/bin/env bash
# Configura el clon: activa los hooks del repo y hace que cada push vaya en paralelo al repo
# de Platanus y a Pleo2/usaprais.com. Corre solo con `pnpm install` (script "prepare") y es
# idempotente. Fuera de un clon de git (por ejemplo, en un build de Docker) no hace nada.
set -euo pipefail
command -v git >/dev/null && git rev-parse --git-dir >/dev/null 2>&1 || exit 0

ORG=git@github.com:platanus-hack/platanus-hack-26-ve-team-10.git
MIRROR=git@github.com:Pleo2/usaprais.com.git

git config core.hooksPath .githooks
git config pull.rebase false   # `git pull origin main` hace merge en tu rama, sin preguntar
git remote add prais "$MIRROR" 2>/dev/null || git remote set-url prais "$MIRROR"
git config --unset-all remote.origin.pushurl || true
git remote set-url --add --push origin "$ORG"
git remote set-url --add --push origin "$MIRROR"
echo "git listo: hooks activos y push en paralelo a Platanus y usaprais.com"
