<script lang="ts">
  import type { PostMatchState, Standing } from "../app-types";

  export let postMatch: PostMatchState | null = null;
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
</script>

<main id="postmatch-view">
  {#if !postMatch}
    <section class="race-empty">
      <p>No completed match data yet.</p>
      <button type="button" class="btn primary" on:click={showHome}>Back Home</button>
    </section>
  {:else}
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
