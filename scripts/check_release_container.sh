#!/usr/bin/env bash
set -Eeuo pipefail
image="${1:?Pass the newly built backend image}"
name="manisov-release-check-$$"
trap 'docker rm -fv "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 4g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:size=256m,mode=1777 \
  --tmpfs /app/uploads:size=16m,uid=10001,gid=10001 \
  --tmpfs /app/generated:size=16m,uid=10001,gid=10001 \
  --tmpfs /app/templates:size=16m,uid=10001,gid=10001 \
  -e MANISOV_ENV=production -e DATABASE_URL=sqlite:////tmp/health.sqlite3 \
  -e AUTO_ALEMBIC_ON_STARTUP=0 -e JWT_SECRET_KEY=container-check-only-0123456789abcdef \
  -e DEFAULT_ADMIN_USERNAME=release-check -e DEFAULT_ADMIN_PASSWORD=release-check-password \
  "$image" >/dev/null
ready=0
for _ in {1..60}; do
  if docker exec "$name" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then docker logs "$name"; exit 1; fi
docker exec "$name" python -c 'import os; from pathlib import Path; assert os.getuid()==10001; assert not os.access("/app/app/main.py", os.W_OK); [Path("/app", p, "check").touch() for p in ("uploads", "generated", "templates")]'
docker exec "$name" python -m pip check
