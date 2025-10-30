#!/usr/bin/env bash
set -euo pipefail
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[mother/INSTALL] Ensuring migrations applied..."
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"
psql "host=${POSTGRES_HOST:-localhost} port=${POSTGRES_PORT:-5432} user=${POSTGRES_USER:-postgres} dbname=${POSTGRES_DB:-health}" -f "$THIS_DIR/db/migrations/all.sql" || true
echo "[mother/INSTALL] Done."
