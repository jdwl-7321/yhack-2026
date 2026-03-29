# AGENTS.md

This file is for future coding agents working in this repository.
It is a living map of the codebase and a maintenance contract to keep that map accurate.

## Core Working Principles (Mandatory)

1. Keep code clean and minimal: no less, and no more.
2. Prefer clarity over cleverness.
3. Refactor when it makes code meaningfully less convoluted and easier to read.
4. Do not leave dead branches, stale comments, or duplicated logic when a small cleanup is safe.
5. Keep behavior unchanged unless the task explicitly asks for behavior changes.

## AGENTS.md Freshness Contract (Mandatory)

When you change code, you must also evaluate whether this file needs updates.
Treat AGENTS.md updates as part of the same task, not optional follow-up.

Update this file whenever you:
- add/remove/rename files
- move logic across files
- change API shapes, endpoint behavior, or key data contracts
- change domain rules (mode fallback, rating, hints, limits, etc.)
- change persistence behavior, startup commands, or test structure

Before finishing any non-trivial task:
1. Re-read the files you changed.
2. Update the relevant sections in AGENTS.md.
3. Remove or correct any stale statements you notice (even outside your immediate change).
4. If uncertain, read code and resolve uncertainty now; do not leave guessed documentation.

If AGENTS.md and code disagree, code is the source of truth, and AGENTS.md must be fixed immediately.

## Repository Overview

Full-stack prototype for a competitive puzzle platform:
- Backend: Flask + Flask-Sock (Python), with in-memory gameplay state and SQLite user persistence.
- Frontend: Svelte + TypeScript (Vite), single-page app with local state and WebSocket live updates.
- Game loop: casual create/join party -> start match -> solve puzzle via Python submission -> standings/rating updates; ranked uses a direct ELO queue that auto-creates 1v1 matches.

Top-level layout:
- `backend/` Python API, game domain, judge, persistence, tests
- `frontend/` Svelte client app
- `README.md` runbook
- `PLAN.md` product/architecture plan and locked decisions
- `DESIGN.md` visual design direction

## Backend Map (`backend/`)

### Entry points and config

- `backend/pyproject.toml`
  - Package name `yhack-backend`, script entry `yhack-backend = "app:main"`.
  - Runtime deps: `flask`, `flask-sock`.
  - Test config points to `backend/tests`.

- `backend/src/run.sh`
  - Local dev runner: `uv run flask --app app run --port 5000 --debug`.

- `backend/src/app.py`
  - Main Flask app wiring (`create_app`, `main`).
  - Defines all REST endpoints and WebSocket endpoint (`/ws/events`).
  - Uses `EventHub` for in-process pub/sub fanout to party/match channels.
  - Converts domain/store objects into API payloads (`_party_payload`, `_match_payload`, `_judge_result_payload`).
  - Also exposes ranked queue payloads via `_ranked_queue_payload`.
  - Enables permissive CORS headers for local frontend dev.
  - Defaults to `SqliteStore` using `backend/data/yhack.sqlite3` unless `YHACK_DB_PATH` is set.

### Domain and rules

- `backend/src/domain_types.py`
  - Shared type aliases/literals: `Mode`, `Difficulty`, JSON types.

- `backend/src/constants.py`
  - Canonical theme catalog (`THEMES`) used by generation and mode logic.

- `backend/src/rating.py`
  - Mode resolution (`ranked` falls back to `casual` if guests exist).
  - Ranked difficulty bucket assignment by average ELO.
  - Ranked matchmaking search window starts narrow and widens over queue wait time.
  - Placement ordering and ELO delta computation.
  - Hint penalty applies only to positive rating gains; level 1 has no penalty, levels 2/3 reduce gain.

- `backend/src/puzzle.py`
  - Puzzle generation core.
  - Defines `TestCase`, `FunctionContract`, `PuzzleInstance`, variable schema parsing/sampling.
  - Generates deterministic sample/hidden tests from `theme + difficulty + seed`.
  - Maintains template registry (`_TEMPLATES`) and mapping by theme/key.
  - Produces `fingerprint` (template/params context) and `signature` (includes all tests) hashes.
  - Renders hints with Jinja templates.
  - Builds solution scaffold from contract.
  - Supports hidden-test replacement (`generate_additional_hidden_test`) for promoted failures.

- `backend/src/judge.py`
  - Sandbox-ish execution for user code using a child process per case (`multiprocessing`).
  - Blocks dangerous builtins (`exec`, `eval`, `open`, `__import__`, etc.).
  - Enforces function existence and arity (`solution(...)`).
  - Runs sample tests first, then hidden tests unless sample-only mode is requested.
  - Captures stdout and returns structured verdict with optional first failed hidden test details.
  - Normalizes comparable output types (list/tuple/dict/set primitives).

- `backend/src/store.py`
  - Core in-memory domain state and gameplay operations.
  - Dataclasses: `User`, `PartySettings`, `Party`, `MatchPlayer`, `Match`, `RankedQueueEntry`.
  - `MemoryStore` handles auth, parties, ranked queue matchmaking, matches, hints, submissions, standings, leaderboard, and finish logic.
  - `SqliteStore` extends `MemoryStore` for persisted users/password hashes/ELO updates.
  - Important behavior:
    - Parties and matches are in-memory only.
    - Ranked queue entries are in-memory only and expire if the client stops polling for ~20 seconds before a match is found.
    - Users are persisted in SQLite only when using `SqliteStore`.
    - Matches in every mode auto-finish when all players are solved or forfeited.
    - Closing a party lobby removes the party, locks any active unfinished match (`locked=True`), and blocks submit/test/hint/forfeit/promote actions for that locked match.
    - Ranked queue only accepts registered users and creates direct 1v1 matches once two queued players fall within the current ELO search window.
    - New matches initialize each player with hint level 1 already available (`hint_level=1`, `hints_used={1}`), so API hint calls unlock levels 2 then 3.
    - Promoting a failed hidden test appends it to visible samples (capped at 4), removes it from hidden set, and generates a replacement hidden case.
    - Ranked theme rotation avoids repeats until all themes are used once.

## Backend API Quick Reference

Defined in `backend/src/app.py`:

- Health/meta:
  - `GET /api/health`
  - `GET /api/themes`
  - `GET /api/generator/schema`
  - `GET /api/leaderboard?limit=`

- Auth/session:
  - `GET /api/auth/session`
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `POST /api/auth/password`

- User utility:
  - `POST /api/users` (direct user creation helper endpoint)

- Party/lobby:
  - `POST /api/parties`
  - `GET /api/parties/<code>`
  - `POST /api/parties/<code>/join`
  - `POST /api/parties/<code>/limit`
  - `POST /api/parties/<code>/settings`
  - `POST /api/parties/<code>/kick`
  - `POST /api/parties/<code>/close`
  - `POST /api/parties/<code>/start`

- Match/gameplay:
  - `GET /api/ranked/queue`
  - `POST /api/ranked/queue`
  - `POST /api/ranked/queue/leave`
  - `GET /api/matches/<match_id>`
  - `POST /api/matches/<match_id>/test` (sample tests only)
  - `POST /api/matches/<match_id>/submit` (sample + hidden; includes `finished` in response)
  - `POST /api/matches/<match_id>/promote-failed-test`
  - `POST /api/matches/<match_id>/hint`
  - `POST /api/matches/<match_id>/forfeit` (includes `finished` in response)
  - `POST /api/matches/<match_id>/finish`

- WebSocket:
  - `GET /ws/events` (Sock route)
  - Client messages: `ping`, `subscribe`, `unsubscribe`
  - Channel naming: `party:<CODE>` and `match:<MATCH_ID>`

## Frontend Map (`frontend/`)

### Build/runtime files

- `frontend/package.json`
  - Scripts: `dev`, `build`, `preview`, `check`.
  - Editor stack includes CodeMirror, Vim plugin, highlight.js, Shiki.

- `frontend/vite.config.ts`
  - Proxies `/api` to `http://localhost:5000` and `/ws` to backend websocket.

- `frontend/src/main.ts`
  - App mount entry.

- `frontend/src/app-types.ts`
  - Central TypeScript contracts for backend payloads and UI state.

- `frontend/src/app.css`
  - Entire app styling and design tokens.
  - Defines theme CSS variables and component layout styles.

### Main SPA orchestrator

- `frontend/src/App.svelte`
  - Large orchestration component (state hub).
  - Responsibilities include:
    - auth/session, account stats localStorage, and stored active-party restore after refresh/login
    - casual party lifecycle, ranked queue polling, and match lifecycle
    - API calls and websocket subscriptions
    - timer and post-match transitions
    - editor behavior (normal/custom shortcuts + custom vim handling)
    - syntax highlighting/theming via highlight.js + Shiki
    - routing between subviews (`home`, `arena`, `leaderboard`, `settings`, `postmatch`)
  - Renders child components and passes state/actions down.

### Svelte component roles

- `frontend/src/components/AppHeader.svelte`
  - Top navigation, quick-settings palette (`Ctrl/Cmd+K`) with persisted last search, theme picker dialog, and account summary dialog.

- `frontend/src/components/HomeView.svelte`
  - Auth card, casual party lobby controls, ranked queue panel, start flow, and active-match resume spotlight/CTA.

- `frontend/src/components/ArenaView.svelte`
  - Match UI: samples, hints, failed hidden case promotion, editor, console, standings.

- `frontend/src/components/LeaderboardView.svelte`
  - Ranked leaderboard display and refresh.

- `frontend/src/components/PostMatchView.svelte`
  - End-of-match summary and final standings board.

- `frontend/src/components/SettingsView.svelte`
  - Appearance/theme controls, keybind profile/custom shortcuts, account/session settings, password change.

### Static assets and legacy prototype

- `frontend/public/favicon.svg`
  - Brand favicon (`<?>` mark).

- `frontend/public/engimga.html`
  - Legacy standalone HTML prototype; not used by Svelte runtime.

## Tests (`backend/tests/`)

- `backend/tests/test_api.py`
  - End-to-end API behavior for auth, parties, ranked queue matchmaking, matches, hints, submissions, promotion, leaderboard, ranked fallback, sqlite persistence.

- `backend/tests/test_judge.py`
  - Judge contract tests: arity checks, verdict flow, stdout capture, shared inputs, normalization.

- `backend/tests/test_puzzle.py`
  - Puzzle schema validation, deterministic generation, cryptography template expectations, scaffold typing.

- `backend/tests/test_rating.py`
  - Difficulty buckets, ranked matchmaking window growth, mode fallback, ordering ties, and hint penalties on rating gains.

## Persistence and State Boundaries

- Persisted:
  - Users (id, name, guest, elo, password hash) in SQLite via `SqliteStore`.

- In-memory only:
  - Parties, ranked queue entries, matches, submissions, hints, standings, event subscriptions, ranked-theme cycle memory.

Implication: server restart drops active parties/matches but keeps user accounts and ELO if SQLite is used.

## Common Task Routing (Where to Edit)

- Add/modify endpoint behavior: `backend/src/app.py` + `backend/src/store.py`
- Change game rules (party limits, hint policy, ranked fallback, ranked matchmaking window, auto-finish): `backend/src/store.py`, `backend/src/rating.py`
- Add new puzzle family/theme/template: `backend/src/puzzle.py` + `backend/src/constants.py` + tests
- Change judging sandbox or verdict details: `backend/src/judge.py` + tests
- Update API payload types in frontend: `frontend/src/app-types.ts`
- Update client flow/state orchestration: `frontend/src/App.svelte`
- Update visual structure by view: corresponding `frontend/src/components/*.svelte`
- Update styling/tokens/layout: `frontend/src/app.css`

## Run and Verify

- Backend dev: `cd backend && uv sync && uv run yhack-backend`
- Backend tests: `cd backend && uv run pytest`
- Frontend dev: `cd frontend && npm install && npm run dev`
- Frontend type checks: `cd frontend && npm run check`

## Known Sharp Edges

- `frontend/src/App.svelte` is very large; prefer extracting cohesive logic into utilities/components when editing substantial new behavior.
- `frontend/public/engimga.html` is not part of active app flow; avoid changing it unless explicitly requested.
- Theme names are validated against `THEMES`; theme/template sync is enforced in `puzzle.py` module initialization.
- Judge security is constrained but still process-based Python execution; treat sandbox changes as security-sensitive.

## Documentation Discipline for Future Agents

When you touch code, update this file with concrete facts, not aspirations.
Keep entries short, precise, and tied to current file paths.
Do not let this file drift.
