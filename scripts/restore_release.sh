#!/usr/bin/env bash
# Restore ONLY to an isolated container and a NEW file directory, never production.
set -Eeuo pipefail
umask 077
[[ $# == 2 ]] || { echo "Usage: bash restore_release.sh BACKUP NEW_EMPTY_DIRECTORY" >&2; exit 2; }
backup="$(realpath "$1")"
destination="$(realpath "$2")"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$backup/COMPLETE" && -d "$destination" && ! -L "$2" ]]
[[ -z "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit)" ]]
(cd "$backup" && sha256sum --check SHA256SUMS)
python3 "$script_dir/deployment_data.py" extract "$backup/files.tar.gz" "$destination"
name="manisov-restore-$(date -u +%Y%m%dT%H%M%SZ)-$$"
password="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
complete=0
cleanup() {
  if [[ "$complete" == 0 ]]; then
    docker rm -fv "$name" >/dev/null 2>&1 || true
    echo "Isolated restore failed; extracted files retained for inspection." >&2
  fi
}
trap cleanup EXIT
# No published ports, production network, or production volume. Anonymous DB volume.
docker run -d --name "$name" --network none --memory 1g --cpus 1 --pids-limit 128 \
  -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=restore postgres:16-alpine >/dev/null
ready=0
for _ in {1..60}; do
  if docker exec "$name" pg_isready -U postgres -d restore >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]]
docker exec -i "$name" pg_restore -U postgres -d restore --no-owner --no-privileges --exit-on-error < "$backup/database.dump"
docker exec "$name" psql -U postgres -d restore -c 'SELECT * FROM alembic_version;'
complete=1
echo "Isolated DB: $name; files: $destination. Production was not modified."
echo "After inspection remove only this container and its anonymous volume: docker rm -fv $name"
