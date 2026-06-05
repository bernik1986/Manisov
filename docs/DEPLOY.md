# Deploy Overview

## Current deploy model

The project is deployed from GitHub to the VPS through GitHub Actions.

Flow:

1. A push lands in `main`
2. GitHub Actions runs `.github/workflows/deploy.yml`
3. The workflow connects to the VPS through SSH
4. On the VPS it runs `deploy.sh`
5. `deploy.sh` synchronizes the repository to `origin/main`
6. `docker compose up -d --build --remove-orphans` rebuilds and restarts the stack

## Required GitHub secrets

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_KEY`

## Required server path

The repository must exist on the VPS at:

`/var/www/Manisov`

If the project lives in a different location, update the path in:

- `.github/workflows/deploy.yml`
- `deploy.sh`

## Runtime stack

`docker-compose.yml` expects these services:

- `db` — PostgreSQL
- `backend` — FastAPI + Alembic migrations on container start
- `frontend` — Vite frontend

## Important note

The backend container already runs:

`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`

Because of that, database migrations are applied automatically during deploy (`deploy.sh` runs `alembic upgrade head` before `docker compose up`, and the backend container runs the same on start).

**Important:** migration scripts live only under `migrations/versions/` (see `alembic.ini`). Do not add new revisions under `alembic/versions/` — that folder is legacy and is not used at runtime.

Additionally, `init_db()` in `models/db.py` runs **`alembic upgrade head`** on application startup when `DATABASE_URL` is **not** SQLite (so Postgres stays in sync even if the process was started without Alembic in `CMD`). Disable with **`AUTO_ALEMBIC_ON_STARTUP=0`**. For short-lived debugging of HTTP 500 responses, you may set **`CREWDECK_EXPOSE_ERROR_DETAIL=1`** on the backend (remove after use).
