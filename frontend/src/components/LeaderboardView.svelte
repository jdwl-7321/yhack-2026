<script lang="ts">
  import type { LeaderboardEntry, SessionUser } from "../app-types";

  type LeaderboardProfilePreview = {
    imageUrl: string;
    initials: string;
    accountType: string;
    rankLabel: string;
    percentileLabel: string;
    statusLabel: string;
    eloLabel: string;
    solveRateLabel: string;
    rankedWinsLabel: string;
    bestHiddenLabel: string;
    sampleRunsLabel: string;
    trackedRunsLabel: string;
  };

  export let leaderboard: LeaderboardEntry[] = [];
  export let sessionUser: SessionUser | null = null;
  export let leaderboardCurrentUser: LeaderboardEntry | null = null;
  export let leaderboardTotalPlayers = 0;
  export let accountInitials: (name: string) => string = () => "EN";
  export let leaderboardProfilePreview: (entry: LeaderboardEntry) => LeaderboardProfilePreview =
    (entry) => ({
      imageUrl: "",
      initials: accountInitials(entry.name),
      accountType: entry.guest ? "Guest session" : "Registered account",
      rankLabel: `#${entry.placement}`,
      percentileLabel: "Top 100%",
      statusLabel: "Ranked",
      eloLabel: `${entry.elo}`,
      solveRateLabel: "--",
      rankedWinsLabel: "--",
      bestHiddenLabel: "--",
      sampleRunsLabel: "--",
      trackedRunsLabel: "--",
    });
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
      <span>Showing the top players ranked by ELO.</span>
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
            {@const profile = leaderboardProfilePreview(row)}
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
                <button type="button" class="leaderboard-profile-trigger">
                  <span class="leaderboard-avatar" aria-hidden={!profile.imageUrl}>
                    {#if profile.imageUrl}
                      <img
                        class="avatar-image"
                        src={profile.imageUrl}
                        alt={`${row.name} profile photo`}
                      />
                    {:else}
                      {accountInitials(row.name)}
                    {/if}
                  </span>
                  <strong>{row.name}</strong>
                  <span class="leaderboard-profile-card">
                    <span class="leaderboard-profile-head">
                      <span class="leaderboard-profile-avatar" aria-hidden={!profile.imageUrl}>
                        {#if profile.imageUrl}
                          <img
                            class="avatar-image"
                            src={profile.imageUrl}
                            alt={`${row.name} profile photo`}
                          />
                        {:else}
                          {profile.initials}
                        {/if}
                      </span>
                      <span class="leaderboard-profile-copy">
                        <span class="eyebrow">Profile</span>
                        <strong>{row.name}</strong>
                        <small>{profile.accountType}</small>
                      </span>
                    </span>
                    <span class="leaderboard-profile-grid">
                      <span>
                        <small>Rank</small>
                        <strong>{profile.rankLabel}</strong>
                      </span>
                      <span>
                        <small>ELO</small>
                        <strong>{profile.eloLabel}</strong>
                      </span>
                      <span>
                        <small>Percentile</small>
                        <strong>{profile.percentileLabel}</strong>
                      </span>
                      <span>
                        <small>Status</small>
                        <strong>{profile.statusLabel}</strong>
                      </span>
                      <span>
                        <small>Solve rate</small>
                        <strong>{profile.solveRateLabel}</strong>
                      </span>
                      <span>
                        <small>Ranked wins</small>
                        <strong>{profile.rankedWinsLabel}</strong>
                      </span>
                      <span>
                        <small>Best hidden</small>
                        <strong>{profile.bestHiddenLabel}</strong>
                      </span>
                      <span>
                        <small>Sample runs</small>
                        <strong>{profile.sampleRunsLabel}</strong>
                      </span>
                      <span>
                        <small>Tracked runs</small>
                        <strong>{profile.trackedRunsLabel}</strong>
                      </span>
                    </span>
                  </span>
                </button>
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
