# yhack-2026 prototype

Initial full-stack prototype for the PLAN.md game loop.

## Stack

- Backend: Flask + Python (managed with `uv`)
- Frontend: Svelte + TypeScript (Vite)

## Quick start

### 1) Backend

```bash
cd backend
uv sync
uv run yhack-backend
```

The API runs on `http://localhost:5000`.
Auth accounts now persist in SQLite at `backend/data/yhack.sqlite3` by default.
Override with `YHACK_DB_PATH=/custom/path.sqlite3`.

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api` to Flask.

## Production deploy (single host)

1) Build the frontend:

```bash
cd frontend
npm install
npm run build
```

2) Install backend deps and run Gunicorn on local port `6767`:

```bash
cd backend
uv sync
YHACK_SECRET_KEY="replace-me" ./src/run-gunicorn.sh
```

Notes:
- The backend serves the built frontend from `frontend/dist` by default.
- Override frontend build location with `YHACK_FRONTEND_DIST=/absolute/path/to/dist`.
- `run-gunicorn.sh` binds to `127.0.0.1:6767` by default (overrides: `YHACK_GUNICORN_HOST`, `YHACK_GUNICORN_PORT`, `YHACK_GUNICORN_THREADS`, `YHACK_GUNICORN_TIMEOUT`).
- `run-gunicorn.sh` enforces `YHACK_GUNICORN_WORKERS=1` because parties, ranked queue entries, and live matches are in-memory and are not shared across worker processes.

3) Nginx TLS reverse proxy config lives at `deploy/nginx/play-enigma.xyz.conf`.
   Copy/symlink it into your Nginx site config directory and reload Nginx.

## Python quality checks

```bash
cd backend
uv run pytest
uvx ty check src tests
```

## Prototype features

- Zen, casual, and ranked mode start flow
- Ranked mode fallback to casual if a guest joins
- Hardcoded theme catalog and seeded puzzle generation
- Hidden/sampled tests with per-puzzle typed function signatures (e.g. `solution(arg1: list[int], arg2: int) -> tuple[int, int]`)
- Two-level hints (`level 2` reveals sampled variable values)
- Ranked placement + ELO delta calculation with hint gain multipliers
- Frontend single-page playable loop with editor and verdict feedback
- UI theme setting: `light`, `dark`, `system`
