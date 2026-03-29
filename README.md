# Enigma

Enigma is a coding game built around hidden-rule puzzles.

Instead of reading a normal problem statement, you look at example input and output behavior, figure out the pattern, and write Python code that matches it.

Live site: [play-enigma.xyz](https://play-enigma.xyz)

## How It Works

Every match starts with a puzzle instance and a Python editor.

You are shown:

- sample inputs
- sample outputs
- the behavior your code needs to match

From there, your job is to infer the rule, write a solution, and test whether your code matches what the puzzle is doing.

If your code passes the visible checks, it is then run against hidden tests. You can also use hints, keep iterating, or forfeit the run.

## Game Modes

### Zen

Zen is the solo mode. It is meant for practice, experimentation, and getting used to the puzzle format without any pressure.

### Casual

Casual is for playing with other people in a more relaxed setting. It is useful for friend lobbies, custom settings, and shared puzzle runs without rating pressure.

### Ranked

Ranked is the competitive mode. Players race on the same puzzle, solve order matters, and results affect rating.

## Local Development

### Backend

```bash
cd backend
uv sync
uv run yhack-backend
```

This starts the backend at `http://localhost:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

This starts the frontend at `http://localhost:5173`.

Requests to `/api` are proxied to the backend during local development.

## Production

### Build the frontend

```bash
cd frontend
npm install
npm run build
```

### Run the backend

```bash
cd backend
uv sync
NOUS_API_KEY="replace-me" ./src/run-gunicorn.sh
```

By default:

- the backend serves the built frontend from `frontend/dist`
- `run-gunicorn.sh` binds to `127.0.0.1:6767`
- the nginx config for the live site is in `deploy/nginx/play-enigma.xyz.conf`

If needed, you can change the frontend build path with `YHACK_FRONTEND_DIST=/absolute/path/to/dist`.

## Checks

### Backend

```bash
cd backend
uv run pytest
uvx ty check src tests
```

### Frontend

```bash
cd frontend
npm run build
```

## Current State

This project is still a prototype, but the main loop is already there:

- account login and guest flows
- Zen, Casual, and Ranked modes
- puzzle generation and judging
- hints and forfeits
- match results and replay flow
- leaderboard and profile views
- editor customization and theme settings

It is already playable at [play-enigma.xyz](https://play-enigma.xyz).
