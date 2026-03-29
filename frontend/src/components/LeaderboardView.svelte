<script lang="ts">
  import type { LeaderboardEntry, SessionUser } from "../app-types";

  export let leaderboard: LeaderboardEntry[] = [];
  export let sessionUser: SessionUser | null = null;
  export let leaderboardCurrentUser: LeaderboardEntry | null = null;
  export let leaderboardTotalPlayers = 0;
  export let leaderboardPercentile: (placement: number) => string = () => "Top 100%";
  export let leaderboardRowNote: (entry: LeaderboardEntry) => string = () => "Ranked";
  export let loadLeaderboard: () => void | Promise<void> = () => {};
</script>

<main id="leaderboard-view">
  <aside class="leaderboard-sidebar">
    <section class="leaderboard-filter-card">
      <p class="eyebrow">Ranked ladder</p>
      <button type="button" class="leaderboard-filter active">
        <i class="fas fa-globe" aria-hidden="true"></i>
        all-time elo
      </button>
    </section>

    <section class="leaderboard-filter-card">
      <p class="eyebrow">Overview</p>
      <div class="leaderboard-stat">
        <span>Players</span>
        <strong>{leaderboardTotalPlayers}</strong>
      </div>
      <div class="leaderboard-stat">
        <span>Your rank</span>
        <strong
          >{leaderboardCurrentUser
            ? `#${leaderboardCurrentUser.placement}`
            : "Unranked"}</strong
        >
      </div>
      <div class="leaderboard-stat">
        <span>Your ELO</span>
        <strong
          >{leaderboardCurrentUser
            ? leaderboardCurrentUser.elo
            : "-"}</strong
        >
      </div>
    </section>
  </aside>

  <section class="leaderboard-main">
    <div class="leaderboard-title-row">
      <div>
        <p class="eyebrow">All-time</p>
        <h1>Ranked Leaderboard</h1>
      </div>
      <span class="leaderboard-badge">{leaderboardTotalPlayers} players</span>
    </div>

    <div class="leaderboard-meta">
      <span>Showing the top ranked players by ELO.</span>
      <button type="button" class="btn" on:click={() => void loadLeaderboard()}>
        Refresh
      </button>
    </div>

    {#if leaderboard.length === 0}
      <section class="leaderboard-empty-state">
        <h2>Leaderboard</h2>
        <p>Registered players will appear here once ranked runs are completed.</p>
      </section>
    {:else}
      <div class="leaderboard-table-wrap">
        <div class="leaderboard-table leaderboard-table-head" role="presentation">
          <span>#</span>
          <span>player</span>
          <span>elo</span>
          <span>percentile</span>
          <span>status</span>
        </div>

        <div class="leaderboard-table-body">
          {#each leaderboard as row}
            <article
              class="leaderboard-table leaderboard-table-row"
              class:current={row.user_id === sessionUser?.id}
            >
              <span class="leaderboard-cell rank">
                {#if row.placement === 1}
                  <i class="fas fa-crown" aria-hidden="true"></i>
                {/if}
                {row.placement}
              </span>
              <span class="leaderboard-cell player">
                <strong>{row.name}</strong>
              </span>
              <span class="leaderboard-cell score">{row.elo}</span>
              <span class="leaderboard-cell percentile">
                {leaderboardPercentile(row.placement)}
              </span>
              <span class="leaderboard-cell note">
                {leaderboardRowNote(row)}
              </span>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </section>
</main>
