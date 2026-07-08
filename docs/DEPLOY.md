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

## Required server env file

Create `/var/www/Manisov/.env` from `.env.example` before starting the stack.
The real `.env` must stay on the server and must not be committed.

Required values:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_FULL_NAME`

## Runtime stack

`docker-compose.yml` expects these services:

- `db` — PostgreSQL
- `backend` — FastAPI + Alembic migrations on container start
- `frontend` — production nginx serving the built Vite frontend

## Production networking

Production exposes only:

- `frontend` on host port `80`
- `db` on `127.0.0.1:5432` for local server maintenance

The `frontend` container is nginx: it serves the built Vite frontend and proxies `/api/*` to `backend:8000` inside the Docker network.
`backend:8000` is not published directly on the public VPS. Do not expose the Vite dev server on production.

## Important note

The backend container already runs:

`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`

Because of that, database migrations are applied automatically during deploy (`deploy.sh` runs `alembic upgrade head` before `docker compose up`, and the backend container runs the same on start).

**Important:** migration scripts live only under `migrations/versions/` (see `alembic.ini`). Do not add new revisions under `alembic/versions/` — that folder is legacy and is not used at runtime.

Additionally, `init_db()` in `models/db.py` runs **`alembic upgrade head`** on application startup when `DATABASE_URL` is **not** SQLite (so Postgres stays in sync even if the process was started without Alembic in `CMD`). Disable with **`AUTO_ALEMBIC_ON_STARTUP=0`**. For short-lived debugging of HTTP 500 responses, you may set **`CREWDECK_EXPOSE_ERROR_DETAIL=1`** on the backend (remove after use).
