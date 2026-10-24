#!/usr/bin/env bash
# Configura el clon una sola vez: activa los hooks del repo y hace que cada push vaya en
# paralelo al repo de Platanus y a Pleo2/prais.com.
set -euo pipefail

ORG=git@github.com:platanus-hack/platanus-hack-26-ve-team-10.git
MIRROR=git@github.com:Pleo2/prais.com.git

git config core.hooksPath .githooks
git config pull.rebase false   # `git pull origin main` hace merge en tu rama, sin preguntar
git remote get-url prais >/dev/null 2>&1 || git remote add prais "$MIRROR"
git config --unset-all remote.origin.pushurl || true
git remote set-url --add --push origin "$ORG"
git remote set-url --add --push origin "$MIRROR"
git remote -v
