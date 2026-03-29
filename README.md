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
