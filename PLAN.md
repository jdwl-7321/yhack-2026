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
2. System generates a puzzle on-demand for the match (theme + difficulty driven by mode rules).
3. User sees:
   - Human-readable puzzle prompt
   - Sample input/output pair(s)
   - Python editor with scaffolded function signature:
     ```python
     def solution(input_str: str) -> str:
         ...
     ```
4. On submit:
   - Run user code on sample tests first
   - If sample passes, run on hidden generated test set
   - Return verdict and partial-credit feedback
5. User can request hints (two levels: directional hint, then full program description reveal).
6. Match/session ends when solved, timeout reached, player forfeits/quits, or party ends.
7. For ranked mode, compute and apply ELO updates.

## 3) Game modes and rules

### Zen mode
- Single-player, no ELO impact
- User can customize theme, difficulty, and time limit
- Theme chosen from a hardcoded dropdown list
- Two-level hints enabled; no rating impact

### Casual multiplayer
- Party leader creates shareable invite link
- No ELO impact
- Party leader controls theme, difficulty, and time limit
- Theme chosen from a hardcoded dropdown list
- Mixed auth state allowed (guest + logged-in)
- Two-level hints enabled; no rating impact

### Ranked multiplayer
- Free-for-all ranking and ELO updates within one room
- All participants must be logged in
- If any participant is guest, fallback to casual mode
- Default time limit is 1 hour; players can forfeit or quit early
- No custom settings (theme/difficulty/time are system-assigned)
- Theme is randomly selected from the hardcoded theme list
- Difficulty is system-assigned from average party ELO
- Hints are always enabled (two levels) and reduce rating gain multiplier
- ELO updates based on placement and performance factors

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
  - Leader controls (theme/difficulty/time) for Zen/Casual only
  - Ranked standings, forfeit/quit state, and end-of-match rating deltas

### Backend (Flask)
- API domains:
  - Auth/session management
  - Puzzle generation and retrieval
  - Matchmaking-lite (party creation/join via link)
  - Submission and judging pipeline
  - Hint generation
  - Forfeit/quit state transitions
  - Ratings and leaderboard
- Realtime transport:
  - WebSocket (preferred) or polling fallback for room updates

### Judge runtime
- Use sandbox executor (e.g., snekbox)
- Load submitted module and call `solution(input_str)` directly (no stdin/stdout contract)
- Strict limits:
  - CPU time
  - Memory
  - Output size
  - Disallowed imports/syscalls
- Deterministic run configuration for fairness and reproducibility

## 5) Data model (initial)

- `users`: account info, auth provider, current ELO, stats
- `sessions`: login sessions / tokens (guest sessions are session-only)
- `parties`: lobby metadata, leader, mode, settings
- `party_members`: membership and readiness state
- `puzzles`: prompt, seed, theme, difficulty, canonical solution metadata
- `test_cases`: sample and hidden tests derived from seed/script
- `matches`: start/end timestamps, mode, settings snapshot, forfeit/quit outcomes
- `submissions`: code, verdict, runtime stats, partial-credit score
- `hints`: hint level requested (1 or 2), text returned, and timing
- `rating_events`: before/after ELO and calculation breakdown

## 6) Puzzle generation pipeline

1. Input:
   - Zen/Casual: selected theme + selected difficulty + optional seed
   - Ranked: random theme + ELO-assigned difficulty + optional seed
2. Use LLM call to produce:
   - Transformation spec
   - Input generator script
   - Reference solver
   - Human-readable description
3. Validate generated assets:
   - Script executes safely
   - Sample/hidden tests generated correctly
   - Reference solver passes all generated tests
4. Persist puzzle package for audit/replay of the exact match.
5. Serve puzzle package to active match.

Generation policy:
- Puzzles are generated on-demand per match (no required pre-generated pool).

Hardcoded theme catalog (initial):
- String manipulation (unix-like text processing)
- Data manipulation (aggregation, mean/median/count/grouping)
- Patterns/math (sequences, arithmetic, combinatorics)
- Parsing and tokenization (logs, delimited records, mixed formats)
- Matrix/grid transformations (rotate/transpose/flood-like rules)
- Encoding/decoding (simple ciphers, base transforms, escaping)
- Stateful simulation (queues/stacks, event steps, finite-state updates)
- Sorting/ranking pipelines (multi-key ordering and filtering)
- Time/date calculations (calendar offsets, intervals, formatting)
- Graph/path-lite puzzles (reachability, shortest-step style rules)

Quality gates:
- Reject ambiguous or inconsistent puzzle packs.
- Tag puzzle difficulty by empirical solve metrics over time.

## 7) Submission and judging flow

Player code contract:
- Submission must define a top-level function `solution(input_str: str) -> str`.
- Judge passes the full raw input text as a single string argument.
- Function must return the full output as a single string (not print).
- Missing function, wrong signature, runtime exception, or non-string return yields a failed verdict.

1. Receive submission and attach to match + user.
2. Compile/execute in sandbox.
3. For each test case, invoke `solution(input_str)` and capture returned string output.
4. Run sample tests and return fast failure feedback.
5. Run hidden tests for final score.
6. Store detailed result:
   - pass/fail per test bucket
   - resource usage
   - normalized partial-credit score
   - passed hidden-test count for player-facing feedback (no hidden test details)
7. Broadcast updated standing in multiplayer rooms.

## 8) ELO design plan

Inputs currently planned (from README):
- Current ELO
- Opponent ELO values
- Puzzle difficulty
- Solve order
- Time to solve
- Partial-credit progress
- Hint usage (including level used)

Proposed approach:
- Use free-for-all ELO updates per ranked room (not head-to-head only)
- Base expected-score model from standard ELO against field average
- Apply bounded modifiers for:
  - Placement rank
  - Completion time percentile
  - Partial-credit level when unsolved
  - Hint usage gain multiplier penalty (reduced positive gain)
  - Difficulty multiplier
- Assign ranked puzzle difficulty from average party ELO before match start
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
  - ranked difficulty assignment from average party ELO
  - hint level penalties on rating gain
  - `solution(input_str) -> str` validator and error handling
  - puzzle package validators
- Integration tests:
  - submission pipeline (sample -> hidden)
  - party lifecycle (create/join/leave/start)
  - forfeit/quit flows and result handling
  - ranked vs casual rules
- End-to-end tests:
  - full solve flow from lobby to results
  - timeout and partial-credit scenarios
  - ranked hint level 1 vs level 2 impact on rating gain
- Security tests:
  - sandbox escape checks
  - resource exhaustion attempts

## 12) Delivery roadmap

Phase 1 (MVP foundation)
- Auth (including guest)
- Party create/join links
- On-demand puzzle generation per match
- Sandbox judge with sample/hidden test flow
- Solo and casual multiplayer gameplay

Phase 2 (competitive layer)
- Ranked mode eligibility enforcement
- Ranked theme randomization and ELO-based difficulty assignment
- ELO engine + rating history
- Results page with rating delta explanation
- Leaderboard + profile stats

Phase 3 (quality and scale)
- Two-level hint system with ranked gain-multiplier penalties
- Puzzle quality scoring and curation
- Performance tuning and queue scaling
- Abuse monitoring and moderation tooling

## 13) Immediate next implementation tasks

1. Define API contract (OpenAPI or equivalent) for auth, parties, matches, submissions, and ratings.
2. Implement database schema + migrations for core entities.
3. Build judge service abstraction around sandbox execution.
4. Implement function-contract execution (`solution(input_str) -> str`) and validator errors.
5. Implement party flow (create/join via share link) and room state updates, including forfeit/quit.
6. Ship first playable loop (single puzzle from start to verdict) with hidden-test count feedback only.
7. Add ranked gating, random ranked theme selection, and ELO-based difficulty assignment.
8. Implement two-level hints and ranked rating-gain multiplier penalties.
9. Add initial free-for-all ELO formula behind feature flag.

## 14) Locked product decisions

1. Ranked multiplayer uses free-for-all ELO in shared rooms.
2. Ranked hints use reduced rating-gain multiplier (no fixed direct ELO penalty).
3. Hints have two levels; level 2 reveals the full program description.
4. Partial credit shows passed hidden-test count only, not hidden test details.
5. Ranked has fixed 1-hour limit, allows forfeit/quit, and has no user customization.
6. Guest accounts are session-only.
7. Puzzles are generated on-demand per match.
8. Theme source is a hardcoded list; Zen/Casual allow selection, Ranked uses random selection.
9. Ranked theme/difficulty are system-assigned, with difficulty based on average party ELO.
10. Player submissions must expose `solution(input_str) -> str`; judge invokes this function per test.

## 15) Optional clarifications to lock later

1. Ranked tie-break priority (solve order, then time, then hidden-test count?)
2. Exact hint multiplier values for level 1 and level 2 in ranked
3. Forfeit/quit rating treatment (fixed floor loss vs performance-based)
4. Difficulty buckets and ELO cutoffs used for ranked assignment
5. Submission cooldown/rate limits to prevent brute-force spam
