#!/usr/bin/env bash
set -euo pipefail

# Full production reset helper:
# - validates required env vars
# - asks for explicit confirmation
# - runs DB reset + admin bootstrap script

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set."
  echo "Example:"
  echo "  export DATABASE_URL='postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME'"
  exit 1
fi

if [[ -z "${DEFAULT_ADMIN_USERNAME:-}" || -z "${DEFAULT_ADMIN_PASSWORD:-}" || -z "${DEFAULT_ADMIN_FULL_NAME:-}" ]]; then
  echo "ERROR: DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_FULL_NAME must be set."
  exit 1
fi

echo "WARNING: This will DELETE ALL DATA in the database configured by DATABASE_URL."
echo "Target admin after reset:"
echo "  username: ${DEFAULT_ADMIN_USERNAME}"
echo "  full name: ${DEFAULT_ADMIN_FULL_NAME}"
echo
read -r -p "Type EXACTLY 'RESET' to continue: " CONFIRM

if [[ "$CONFIRM" != "RESET" ]]; then
  echo "Aborted."
  exit 1
fi

echo "Starting destructive reset..."
python3 scripts/reset_db_and_bootstrap_admin.py --yes
echo "Done."
