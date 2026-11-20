#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_DIR="${APP_DIR:-/var/www/Manisov}"
STATE_DIR="${STATE_DIR:-/var/lib/manisov-deploy}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOCK_FILE="${LOCK_FILE:-/var/lock/manisov-deploy.lock}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "${QUIESCENCE_CONFIRMED:-}" == "yes" ]] || {
  echo "Stop external DB/file writers and set QUIESCENCE_CONFIRMED=yes." >&2; exit 2;
}
# Timer and Actions call this entry point without taking a second outer lock.
exec 9>"$LOCK_FILE"
flock -w "${LOCK_TIMEOUT:-3600}" 9
mkdir -p "$STATE_DIR/releases" "$STATE_DIR/backups"
[[ ! -e "$STATE_DIR/maintenance" ]] || {
  echo "Unresolved maintenance state: $STATE_DIR/maintenance. Operator recovery required." >&2; exit 1;
}
git -C "$APP_DIR" fetch --no-tags origin main
if [[ "${1:-}" == "--timer" ]]; then
  DEPLOY_SHA="$(git -C "$APP_DIR" rev-parse origin/main^{commit})"
fi
: "${DEPLOY_SHA:?Pass the exact tested 40-character commit SHA, or use --timer}"
[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid DEPLOY_SHA" >&2; exit 2; }
python3 "$SCRIPT_DIR/scripts/deployment_ci.py" "$DEPLOY_SHA"
git -C "$APP_DIR" merge-base --is-ancestor "$DEPLOY_SHA" origin/main
[[ "$(git -C "$APP_DIR" rev-parse origin/main^{commit})" == "$DEPLOY_SHA" ]] || {
  echo "A newer main commit exists; refusing a stale queued deployment." >&2; exit 1;
}
[[ "$(git -C "$APP_DIR" rev-parse "$DEPLOY_SHA^{commit}")" == "$DEPLOY_SHA" ]]
if [[ -f "$STATE_DIR/current" ]]; then
  current="$(cat "$STATE_DIR/current")"
  if [[ -f "$current/images.env" ]] && grep -qx "DEPLOY_SHA=$DEPLOY_SHA" "$current/images.env"; then
    echo "[deploy] Commit already released: $DEPLOY_SHA"
    exit 0
  fi
fi

release="$STATE_DIR/releases/$DEPLOY_SHA-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$release"
git -C "$APP_DIR" archive "$DEPLOY_SHA" | tar -x -C "$release"
export BACKEND_IMAGE="manisov-backend:$(basename "$release")"
export FRONTEND_IMAGE="manisov-frontend:$(basename "$release")"
dc() { docker compose --env-file "$ENV_FILE" --project-directory "$APP_DIR" -f "$release/docker-compose.yml" "$@"; }
dc config --format json | python3 "$release/scripts/deployment_data.py" config
# No live source sync/reset, migrations, downtime or data mutation before BOTH builds pass.
docker build -t "$BACKEND_IMAGE" -f "$release/Dockerfile" "$release"
docker build -t "$FRONTEND_IMAGE" -f "$release/app/frontend/Dockerfile" "$release/app/frontend"
export BACKEND_IMAGE="$(docker image inspect --format '{{.Id}}' "$BACKEND_IMAGE")"
export FRONTEND_IMAGE="$(docker image inspect --format '{{.Id}}' "$FRONTEND_IMAGE")"
printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\nDEPLOY_SHA=%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "$DEPLOY_SHA" > "$release/images.env"
chmod -R a-w "$release"

# Never create a new/empty DB implicitly or replace/upgrade PostgreSQL during app deploy.
db_id="$(dc ps -q db)"
[[ -n "$db_id" ]] || { echo "Existing DB service required; see deployment runbook." >&2; exit 1; }
[[ "$(docker inspect --format '{{.State.Health.Status}}' "$db_id")" == "healthy" ]]
backend_id="$(dc ps -a -q backend)"
dc config --format json | python3 "$SCRIPT_DIR/scripts/deployment_data.py" database "$db_id" "$backend_id"

old_ids=()
ids="$(dc ps -q backend frontend)"
while IFS= read -r id; do [[ -z "$id" ]] || old_ids+=("$id"); done <<< "$ids"
quiesced=0
migration_started=0
completed=0
migrator="manisov-migrate-$(basename "$release")"
finish() {
  rc=$?
  trap - EXIT INT TERM HUP
  if [[ "$completed" == 0 && "$quiesced" == 1 ]]; then
    docker rm -f "$migrator" >/dev/null 2>&1 || true
    if [[ "$migration_started" == 0 ]]; then
      # Existing containers only: no rebuild, no schema rollback, no data restore.
      if (( ${#old_ids[@]} )); then
        docker update --restart=unless-stopped "${old_ids[@]}" >/dev/null &&
          docker start "${old_ids[@]}" >/dev/null &&
          rm -f "$STATE_DIR/maintenance"
      else
        rm -f "$STATE_DIR/maintenance"
      fi
    else
      printf '%s\n' "$release" > "$STATE_DIR/maintenance"
      failed_ids="$(dc ps -a -q backend frontend)" || failed_ids=""
      while IFS= read -r id; do
        [[ -z "$id" ]] || docker update --restart=no "$id" >/dev/null || true
      done <<< "$failed_ids"
      dc stop -t 60 frontend backend || true
      echo "Release failed after migration began. Services remain OFFLINE; no automatic DB restore." >&2
      echo "Backup: ${backup:-not-completed}; release: $release" >&2
    fi
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
printf '%s\n' "$release" > "$STATE_DIR/maintenance"
quiesced=1
if (( ${#old_ids[@]} )); then docker update --restart=no "${old_ids[@]}" >/dev/null; fi
dc stop -t 60 frontend backend
# Reject other database clients at the checkpoint; external schedulers MUST stay stopped.
connections="$(dc exec -T db sh -ec 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()"')"
[[ "$connections" == 0 ]] || { echo "Other database clients remain; refusing snapshot." >&2; exit 1; }

backup="$STATE_DIR/backups/$(basename "$release")"
mkdir "$backup"
dc exec -T db sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$backup/database.dump"
dc exec -T db pg_restore --list < "$backup/database.dump" > "$backup/database.list"
dc run --rm -T --no-deps --pull never --user 0:0 --cap-add DAC_OVERRIDE backend tar -C /app -czf - uploads templates > "$backup/files.tar.gz"
tar -tzf "$backup/files.tar.gz" > "$backup/files.list"
cp "$release/images.env" "$backup/new-images.env"
printf '%s\n' "$db_id" > "$backup/database-container"
if (( ${#old_ids[@]} )); then docker inspect "${old_ids[@]}" > "$backup/previous-containers.json"; fi
(cd "$backup" && sha256sum database.dump files.tar.gz > SHA256SUMS)
touch "$backup/COMPLETE"

# Root is restricted to the three data binds, never application source.
dc run --rm -T --no-deps --pull never --user 0:0 --cap-add CHOWN --cap-add FOWNER --cap-add DAC_OVERRIDE backend python scripts/deployment_data.py prepare
migration_started=1
dc run --rm -T --no-deps --pull never --name "$migrator" backend alembic upgrade head
dc up -d --no-build --pull never --no-deps --wait --wait-timeout 180 backend
dc up -d --no-build --pull never --no-deps --wait --wait-timeout 120 frontend
# nginx checks both the SPA and /api/healthz, not just process liveness.
dc exec -T frontend wget -q -O /dev/null http://127.0.0.1/api/healthz
new_ids=()
ids="$(dc ps -q backend frontend)"
while IFS= read -r id; do [[ -z "$id" ]] || new_ids+=("$id"); done <<< "$ids"
(( ${#new_ids[@]} == 2 ))
docker update --restart=unless-stopped "${new_ids[@]}" >/dev/null
printf '%s\n' "$release" > "$STATE_DIR/current.tmp"
mv "$STATE_DIR/current.tmp" "$STATE_DIR/current"
rm -f "$STATE_DIR/maintenance"
completed=1
echo "[deploy] Healthy release $DEPLOY_SHA; backup $backup"
