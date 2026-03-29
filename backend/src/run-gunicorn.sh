#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${YHACK_GUNICORN_HOST:-127.0.0.1}"
PORT="${YHACK_GUNICORN_PORT:-6767}"
WORKERS="${YHACK_GUNICORN_WORKERS:-1}"
THREADS="${YHACK_GUNICORN_THREADS:-8}"
TIMEOUT="${YHACK_GUNICORN_TIMEOUT:-120}"

if ! [[ "${WORKERS}" =~ ^[0-9]+$ ]] || [ "${WORKERS}" -lt 1 ]; then
  echo "YHACK_GUNICORN_WORKERS must be a positive integer" >&2
  exit 1
fi

if [ "${WORKERS}" -ne 1 ]; then
  echo "This app keeps parties, ranked queue, and matches in process memory." >&2
  echo "Set YHACK_GUNICORN_WORKERS=1 to avoid cross-worker state loss." >&2
  exit 1
fi

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
