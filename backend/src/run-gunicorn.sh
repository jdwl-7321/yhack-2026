#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${YHACK_GUNICORN_HOST:-127.0.0.1}"
PORT="${YHACK_GUNICORN_PORT:-6767}"
WORKERS="${YHACK_GUNICORN_WORKERS:-2}"
THREADS="${YHACK_GUNICORN_THREADS:-8}"
TIMEOUT="${YHACK_GUNICORN_TIMEOUT:-120}"

uv run gunicorn \
  --chdir "${SCRIPT_DIR}" \
  --bind "${HOST}:${PORT}" \
  --worker-class gthread \
  --workers "${WORKERS}" \
  --threads "${THREADS}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"
