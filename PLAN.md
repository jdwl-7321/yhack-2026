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
5. User can request hints (two levels: directional hint, then full program description reveal including sampled variable values).
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
- Quit/forfeit is treated as unsolved for ranking/rating (same as not solving within the hour)
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
  - Generator contract for variable schema + novelty controls
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
- `puzzles`: prompt, seed, theme, difficulty, canonical solution metadata, parameter schema, novelty fingerprint
- `puzzle_instances`: per-match resolved parameter values and frozen generated assets used for judging
- `test_cases`: sample and hidden tests derived from seed/script
- `matches`: start/end timestamps, mode, settings snapshot, forfeit/quit outcomes
- `submissions`: code, verdict, runtime stats, partial-credit score
- `hints`: hint level requested (1 or 2), text returned, and timing
- `rating_events`: before/after ELO and calculation breakdown
- `novelty_pool`: rolling window of recent puzzle fingerprints/signatures with recency rank

## 6) Puzzle generation pipeline

1. Input:
   - Zen/Casual: selected theme + selected difficulty + optional seed
   - Ranked: random theme + ELO-assigned difficulty + optional seed
   - Optional variable constraints for parameterized puzzle logic (name/type/range)
2. Use LLM call to produce:
   - Transformation spec
   - Input generator script
   - Reference solver
   - Human-readable description
   - Parameter schema used by the puzzle template
3. Validate generated assets:
   - Script executes safely
   - Sample/hidden tests generated correctly
   - Reference solver passes all generated tests
   - Parameter schema is valid (types, ranges, names)
4. Run novelty check against rolling pool (exact and near-duplicate fingerprint checks); regenerate on collision up to retry budget.
5. Sample concrete parameter values for the match from validated ranges using seedable RNG.
6. Generate sample + hidden tests using this fixed parameter assignment for the full match.
7. Persist puzzle template + per-match puzzle instance for audit/replay.
8. Serve puzzle instance to active match.

Generation policy:
- Puzzles are generated on-demand per match (no required pre-generated pool).
- Novelty is enforced against a rolling pool size (`NOVELTY_POOL_SIZE`) of 50 to reduce repeats.

Parameterized puzzle variable contract:
- Generator request may include `variables`, an optional list of constraints:
  - `name`: identifier used by transformation logic (e.g., `n`)
  - `type`: `int | float | bool | str | choice`
  - `sampling`: backend RNG policy returned by generator for this variable (`uniform`, `weighted`, or `fixed_list`)
  - `range`:
    - numeric: `{ "min": <number>, "max": <number>, "inclusive": true|false }`
    - string: `{ "min_length": <int>, "max_length": <int>, "charset": "..." }`
    - choice: `{ "options": [ ... ] }`
- Example request shape:
  - `{ "variables": [{ "name": "n", "type": "int", "range": { "min": 2, "max": 20, "inclusive": true } }] }`
- At match creation, values are sampled once per variable and frozen for that match.
- Concrete variable values are sampled by backend code RNG (not by the LLM).
- Sampled variable values are hidden during normal play.
- Final hint (level 2) includes the full human description with the sampled variable values.
- All sample and hidden outputs for that match must be computed with the same sampled variable values.

Novelty strategy:
- Build a normalized fingerprint from transformation spec + parameter schema + theme + difficulty.
- Reject exact fingerprint matches in the last `NOVELTY_POOL_SIZE` accepted puzzles.
- Reject near-duplicates using an initial similarity threshold over normalized signatures (0.88, tunable).
- On rejection, regenerate with stronger novelty hints until retry limit; if exhausted, return controlled failure.

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
- Reject templates with unconstrained or unsafe variable ranges.

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
- Initial player rating starts at 1000.
- Use free-for-all ELO updates per ranked room (not head-to-head only)
- Base expected-score model from standard ELO against field average
- Ranked placement order:
  - Solved players first, ordered by earliest accepted full-solve timestamp
  - Unsolved players next, ordered by hidden-test count, then earliest time reaching best score
  - Quit/forfeit players are scored as unsolved using their best score at quit time
- Initial difficulty assignment plan from average party ELO (tunable):
  - `< 900`: Easy
  - `900-1099`: Medium
  - `1100-1299`: Hard
  - `>= 1300`: Expert
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
- Initial common-sense defaults: short submit cooldown, per-match/hour submit caps, one request per hint level, and capped room creation/join attempts
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
  - ranked placement tie-break ordering and quit-as-unsolved behavior
  - mode eligibility and fallback logic
  - ranked difficulty assignment from average party ELO
  - hint level penalties on rating gain
  - `solution(input_str) -> str` validator and error handling
  - variable schema validator and per-type range parsing
  - variable sampling modes (`uniform`, `weighted`, `fixed_list`)
  - deterministic parameter sampling from seed
  - novelty fingerprint generation and duplicate detection
  - novelty pool eviction behavior at size 50
  - puzzle package validators
- Integration tests:
  - submission pipeline (sample -> hidden)
  - party lifecycle (create/join/leave/start)
  - forfeit/quit flows and result handling
  - parameterized puzzle generation with frozen match variables
  - novelty retry path and graceful failure when retry budget is exhausted
  - submission/hint/room rate-limit enforcement paths
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
2. Define generator payload/response schema including variable constraints (`name`, `type`, `range`, `sampling`) and novelty controls.
3. Implement database schema + migrations for core entities, puzzle instances, and novelty pool tracking.
4. Build judge service abstraction around sandbox execution.
5. Implement function-contract execution (`solution(input_str) -> str`) and validator errors.
6. Implement parameter sampling and freeze-per-match puzzle instances.
7. Implement novelty fingerprint checks with rolling pool + retry budget.
8. Implement party flow (create/join via share link) and room state updates, including forfeit/quit.
9. Ship first playable loop (single puzzle from start to verdict) with hidden-test count feedback only.
10. Add ranked gating, random ranked theme selection, and ELO-based difficulty assignment buckets.
11. Implement two-level hints and ranked rating-gain multiplier penalties.
12. Add initial free-for-all ELO formula, tie-break ordering, and quit-as-unsolved handling behind feature flag.
13. Implement common-sense submission/hint/room rate limits and related monitoring.

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
11. Puzzle templates may declare typed variables with bounded ranges; match instances sample and freeze values.
12. Generator enforces novelty using a bounded rolling pool to reduce duplicate puzzles.
13. Sampled variable values stay hidden during normal play and are revealed in the final hint description.
14. Ranked tie-break order uses earliest full-solve time, then hidden-test progress for unsolved players.
15. Quit/forfeit is equivalent to not solving within the ranked one-hour window.
16. Initial player ELO starts at 1000.
17. Initial ranked difficulty buckets are based on average party ELO and are tuning-friendly.
18. Submission/hint/room protections use common-sense rate limits from launch.
19. `NOVELTY_POOL_SIZE` is set to 50 for initial rollout.
20. Variable sampling policy comes from the generator schema, but concrete RNG is executed in backend code.

## 15) Optional clarifications to lock later

1. Exact hint multiplier values for level 1 and level 2 in ranked
2. Tuning targets for near-duplicate similarity threshold after telemetry
3. Tuning targets for ranked difficulty bucket cutoffs after telemetry
