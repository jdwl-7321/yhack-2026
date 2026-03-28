# yhack-2026 Implementation Plan

## 1) Project goals and scope

Build an online competitive puzzle platform where players infer a hidden transformation rule from sample input/output, then submit Python code that reproduces the behavior on hidden generated tests.

Primary goals:
- Fun, fast puzzle-solving loop for solo and multiplayer play
- Fair judging and anti-cheat sandboxing
- Competitive ranked experience with ELO
- Casual and Zen modes for experimentation and social play

Out-of-scope for first release:
- Auto-matchmaking
- Non-Python programming languages
- Mobile native apps

## 2) Core game loop (MVP)

1. User chooses mode (Zen, Casual Multiplayer, Ranked Multiplayer).
2. System creates or selects a puzzle (theme + difficulty driven).
3. User sees:
   - Human-readable puzzle prompt
   - Sample input/output pair(s)
   - Python editor
4. On submit:
   - Run user code on sample tests first
   - If sample passes, run on hidden generated test set
   - Return verdict and partial-credit feedback
5. If enabled for mode, user can request hints.
6. Match/session ends when solved, timeout reached, or party ends.
7. For ranked mode, compute and apply ELO updates.

## 3) Game modes and rules

### Zen mode
- Single-player, no ELO impact
- User can customize theme, difficulty, and time limit
- Hints allowed with no rating penalty

### Casual multiplayer
- Party leader creates shareable invite link
- No ELO impact
- Party leader controls theme, difficulty, and time limit
- Mixed auth state allowed (guest + logged-in)

### Ranked multiplayer
- All participants must be logged in
- If any participant is guest, fallback to casual mode
- ELO updates based on placement and performance factors
- Hints allowed but reduce rating gain (or add rating penalty)

## 4) System architecture

### Frontend (Svelte + TypeScript + Tailwind)
- Pages:
  - Landing/home
  - Auth (login/register/guest entry)
  - Lobby (create/join party)
  - Game room (editor, timer, submissions, hints)
  - Results/rating changes
  - Profile/history
- Realtime features:
  - Party membership updates
  - Submission status updates
  - Leader controls (theme/difficulty/time)

### Backend (Flask)
- API domains:
  - Auth/session management
  - Puzzle generation and retrieval
  - Matchmaking-lite (party creation/join via link)
  - Submission and judging pipeline
  - Hint generation
  - Ratings and leaderboard
- Realtime transport:
  - WebSocket (preferred) or polling fallback for room updates

### Judge runtime
- Use sandbox executor (e.g., snekbox)
- Strict limits:
  - CPU time
  - Memory
  - Output size
  - Disallowed imports/syscalls
- Deterministic run configuration for fairness and reproducibility

## 5) Data model (initial)

- `users`: account info, auth provider, current ELO, stats
- `sessions`: login sessions / tokens
- `parties`: lobby metadata, leader, mode, settings
- `party_members`: membership and readiness state
- `puzzles`: prompt, seed, theme, difficulty, canonical solution metadata
- `test_cases`: sample and hidden tests derived from seed/script
- `matches`: start/end timestamps, mode, settings snapshot
- `submissions`: code, verdict, runtime stats, partial-credit score
- `hints`: requested hint text + timing
- `rating_events`: before/after ELO and calculation breakdown

## 6) Puzzle generation pipeline

1. Input: selected theme + difficulty + optional seed.
2. Use LLM call to produce:
   - Transformation spec
   - Input generator script
   - Reference solver
   - Human-readable description
3. Validate generated assets:
   - Script executes safely
   - Sample/hidden tests generated correctly
   - Reference solver passes all generated tests
4. Persist puzzle package and cache for reuse.
5. Serve puzzle package to active match.

Quality gates:
- Reject ambiguous or inconsistent puzzle packs.
- Tag puzzle difficulty by empirical solve metrics over time.

## 7) Submission and judging flow

1. Receive submission and attach to match + user.
2. Compile/execute in sandbox.
3. Run sample tests and return fast failure feedback.
4. Run hidden tests for final score.
5. Store detailed result:
   - pass/fail per test bucket
   - resource usage
   - normalized partial-credit score
6. Broadcast updated standing in multiplayer rooms.

## 8) ELO design plan

Inputs currently planned (from README):
- Current ELO
- Opponent ELO values
- Puzzle difficulty
- Solve order
- Time to solve
- Partial-credit progress
- Hint usage (ranked penalty)

Proposed approach:
- Base expected-score model from standard ELO against field average
- Apply bounded modifiers for:
  - Placement rank
  - Completion time percentile
  - Partial-credit level when unsolved
  - Hint usage penalty
  - Difficulty multiplier
- Cap total per-match delta to prevent extreme swings

## 9) Security and abuse prevention

- Sandbox isolation and strict runtime quotas
- Rate limits on submissions, hints, and room creation
- Auth checks for ranked eligibility
- Signed/expiring invite links
- Audit logs for judging and rating events
- Basic anti-collusion heuristics for ranked parties

## 10) Observability and operations

- Structured logs for API, judge, and websocket events
- Metrics:
  - judge latency
  - submission pass rate
  - solve time by difficulty
  - hint usage rate
  - queue depth and sandbox failures
- Alerts for high judge failure rates and latency spikes

## 11) Testing strategy

- Unit tests:
  - ELO calculations
  - mode eligibility and fallback logic
  - puzzle package validators
- Integration tests:
  - submission pipeline (sample -> hidden)
  - party lifecycle (create/join/leave/start)
  - ranked vs casual rules
- End-to-end tests:
  - full solve flow from lobby to results
  - timeout and partial-credit scenarios
- Security tests:
  - sandbox escape checks
  - resource exhaustion attempts

## 12) Delivery roadmap

Phase 1 (MVP foundation)
- Auth (including guest)
- Party create/join links
- Basic puzzle generation + caching
- Sandbox judge with sample/hidden test flow
- Solo and casual multiplayer gameplay

Phase 2 (competitive layer)
- Ranked mode eligibility enforcement
- ELO engine + rating history
- Results page with rating delta explanation
- Leaderboard + profile stats

Phase 3 (quality and scale)
- Hint system with ranked penalties
- Puzzle quality scoring and curation
- Performance tuning and queue scaling
- Abuse monitoring and moderation tooling

## 13) Immediate next implementation tasks

1. Define API contract (OpenAPI or equivalent) for auth, parties, matches, submissions, and ratings.
2. Implement database schema + migrations for core entities.
3. Build judge service abstraction around sandbox execution.
4. Implement party flow (create/join via share link) and room state updates.
5. Ship first playable loop (single puzzle from start to verdict).
6. Add ranked gating and initial ELO formula behind feature flag.

## 14) Open clarifications needed

1. Ranked multiplayer format: free-for-all in one room, or head-to-head only?
2. Hint behavior in ranked: fixed ELO penalty, reduced gain multiplier, or both?
3. Partial credit visibility: show exact passed test count, coarse tiers, or hidden?
4. Time limit defaults/ranges per difficulty and per mode?
5. Guest account persistence: session-only, or upgradable guest profile?
6. Puzzle generation strategy: generate on-demand per match or pre-generate a pool?
7. Should ranked allow custom theme/difficulty, or should those be system-assigned for fairness?
