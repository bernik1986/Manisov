#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/Manisov}"
BRANCH="${BRANCH:-main}"

echo "[deploy] Starting deploy in ${APP_DIR} from branch ${BRANCH}"
cd "${APP_DIR}"

if [[ "${SKIP_GIT_SYNC:-0}" != "1" ]]; then
  echo "[deploy] Syncing repository"
  git fetch origin
  git reset --hard "origin/${BRANCH}"
else
  echo "[deploy] Repository sync skipped because SKIP_GIT_SYNC=1"
fi

echo "[deploy] Applying database migrations"
docker compose run --rm --no-deps backend alembic current || true
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps backend alembic current

echo "[deploy] Rebuilding and starting containers"
docker compose up -d --build --remove-orphans

echo "[deploy] Current container status"
docker compose ps
