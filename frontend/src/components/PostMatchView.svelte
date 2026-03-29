<script lang="ts">
  import type { PostMatchState, SessionUser, Standing } from "../app-types";

  // Flip this to false if you want to remove the win confetti quickly.
  const SHOW_POSTMATCH_CONFETTI = true;
  const CONFETTI_COLORS = [
    "var(--main-color)",
    "var(--editor-function)",
    "var(--editor-string)",
    "var(--editor-number)",
    "var(--text-color)",
  ];
  const CONFETTI_PIECES = Array.from({ length: 28 }, (_, index) => ({
    id: index,
    left: (index * 13 + 7) % 100,
    delay: (index % 7) * 0.14,
    duration: 3.2 + (index % 5) * 0.35,
    drift: (index % 2 === 0 ? 1 : -1) * (18 + (index % 4) * 10),
    size: 0.42 + (index % 3) * 0.14,
    color: CONFETTI_COLORS[index % CONFETTI_COLORS.length],
    shape: index % 4 === 0 ? "circle" : "rect",
  }));

  export let postMatch: PostMatchState | null = null;
  export let sessionUser: SessionUser | null = null;
  export let matchId: string | null = null;
  export let notice = "";
  export let error = "";

  export let showHome: () => void = () => {};
  export let showArena: () => void = () => {};
  export let postMatchWinner: (rows: Standing[]) => Standing | null = () => null;
  export let postMatchSolvedCount: (rows: Standing[]) => number = () => 0;
  export let postMatchForfeitCount: (rows: Standing[]) => number = () => 0;
  export let formatDuration: (totalSeconds: number) => string = () => "0:00";
  export let formatRatingDelta: (value: number) => string = (value) => String(value);

  $: winner = postMatch ? postMatchWinner(postMatch.standings) : null;
  $: celebrateWin =
    SHOW_POSTMATCH_CONFETTI &&
    !!postMatch &&
    !!sessionUser &&
    !!winner &&
    winner.user_id === sessionUser.id &&
    !winner.forfeited;
</script>

<main id="postmatch-view">
  {#if !postMatch}
    <section class="race-empty">
      <p>No completed match data yet.</p>
      <button type="button" class="btn primary" on:click={showHome}>Back Home</button>
    </section>
  {:else}
    {#if celebrateWin}
      <div class="postmatch-confetti" aria-hidden="true">
        {#each CONFETTI_PIECES as piece (piece.id)}
          <span
            class="postmatch-confetti-piece"
            class:circle={piece.shape === "circle"}
            style={`--confetti-left: ${piece.left}%; --confetti-delay: ${piece.delay}s; --confetti-duration: ${piece.duration}s; --confetti-drift: ${piece.drift}px; --confetti-size: ${piece.size}rem; --confetti-color: ${piece.color};`}
          ></span>
        {/each}
      </div>
    {/if}

    <section class="postmatch-hero">
      <div>
        <p class="eyebrow">Match complete</p>
        <h1>{postMatch.mode.toUpperCase()} Results</h1>
        <p class="postmatch-subtitle">
          {postMatch.reason} · {postMatch.theme} · {postMatch.difficulty}
        </p>
      </div>
      <div class="postmatch-actions">
        <button type="button" class="btn" on:click={showHome}>Home</button>
        <button type="button" class="btn" on:click={showArena} disabled={!matchId}
          >View Arena</button
        >
      </div>
    </section>

    <section class="postmatch-stats-grid">
      <article class="postmatch-stat-card">
        <span class="eyebrow">Winner</span>
        <strong>{postMatchWinner(postMatch.standings)?.name ?? "No winner"}</strong>
      </article>
      <article class="postmatch-stat-card">
        <span class="eyebrow">Solved</span>
        <strong>{postMatchSolvedCount(postMatch.standings)}/{postMatch.standings.length}</strong>
      </article>
      <article class="postmatch-stat-card">
        <span class="eyebrow">Forfeits</span>
        <strong>{postMatchForfeitCount(postMatch.standings)}</strong>
      </article>
      <article class="postmatch-stat-card">
        <span class="eyebrow">Time Limit</span>
        <strong>{formatDuration(postMatch.time_limit_seconds)}</strong>
      </article>
    </section>

    <section class="postmatch-board">
      <div class="standings-head">
        <h3>Final board</h3>
      </div>
      <div class="standings-list">
        {#each postMatch.standings as row}
          <article class="standing-row">
            <span class="mono">#{row.placement}</span>
            <span class="name">{row.name}</span>
            <span class="mono">hidden {row.hidden_passed}</span>
            <span class="mono">hint {row.hint_level}</span>
            <span class="mono">ELO {row.elo}</span>
            <span class="mono delta">{formatRatingDelta(row.rating_delta)}</span>
            <span class="state" class:ok={row.solved} class:bad={!row.solved}>
              {row.forfeited ? "FORFEIT" : row.solved ? "SOLVED" : "OPEN"}
            </span>
          </article>
        {/each}
      </div>
    </section>
  {/if}
  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error}
    <p class="flash error">{error}</p>
  {/if}
</main>
