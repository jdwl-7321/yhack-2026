<script lang="ts">
  import type { BundledTheme } from "shiki/bundle/web";
  import type {
    AccountStats,
    AppearanceMode,
    SessionUser,
    UiTheme,
    View,
  } from "../app-types";

  export let activeView: View = "home";
  export let appearanceMode: AppearanceMode = "system";
  export let themeStatusText = "";
  export let activeEditorThemeName = "";
  export let themePref: UiTheme = "dark";
  export let activeEditorTheme: BundledTheme = "github-dark-default";
  export let availableEditorThemes: Array<{ id: string; displayName: string }> = [];

  export let sessionUser: SessionUser | null = null;
  export let accountStats: AccountStats = {
    matchesStarted: 0,
    matchesSolved: 0,
    rankedFinished: 0,
    rankedWins: 0,
    hintsUsed: 0,
    sampleRuns: 0,
    submissions: 0,
    forfeits: 0,
    bestHiddenPassed: 0,
    recentRuns: [],
    recordedMatchIds: [],
  };
  export let accountSolveRate: number | null = null;
  export let accountRankLabel = "Unranked";
  export let accountPercentileLabel = "No ranked result yet";
  export let accountRankedWinLabel = "0/0";
  export let leaderboardTotalPlayers = 0;
  export let matchSummaryLabel = "No active match";
  export let hasActiveMatch = false;
  export let busy = false;

  export let themeMenuOpen = false;
  export let accountMenuOpen = false;
  export let themeMenuEl: HTMLDivElement | null = null;
  export let accountMenuEl: HTMLDivElement | null = null;

  export let showHome: () => void = () => {};
  export let showPlayView: () => void = () => {};
  export let toggleLeaderboardView: () => void = () => {};
  export let showSettings: () => void = () => {};
  export let cycleAppearanceMode: () => void = () => {};
  export let toggleThemeMenu: () => void = () => {};
  export let toggleAccountMenu: () => void = () => {};
  export let setEditorTheme: (themeId: BundledTheme) => void = () => {};
  export let accountInitials: (name: string) => string = () => "EN";
  export let formatActivityTime: (timestamp: string) => string = () => "";
  export let formatRatingDelta: (value: number) => string = (value) => String(value);
  export let showArena: () => void = () => {};
  export let logout: () => void | Promise<void> = () => {};
</script>

<header>
  <button type="button" class="logo" on:click={showHome}>
    <span class="logo-mark" aria-hidden="true">
      <i class="fas fa-angle-left"></i>
      <i class="fas fa-question logo-mark-question"></i>
      <i class="fas fa-angle-right"></i>
    </span>
    <span class="text">enigma</span>
  </button>

  <nav aria-label="Primary">
    <button
      type="button"
      class="nav-icon"
      class:active={activeView === "home" || activeView === "arena"}
      on:click={showPlayView}
      title="Play"
    >
      <i class="fas fa-gamepad" aria-hidden="true"></i>
    </button>
    <button
      type="button"
      class="nav-icon"
      class:active={activeView === "leaderboard"}
      on:click={toggleLeaderboardView}
      title="Leaderboard"
    >
      <i class="fas fa-crown" aria-hidden="true"></i>
    </button>
    <button
      type="button"
      class="nav-icon"
      class:active={activeView === "settings"}
      on:click={showSettings}
      title="Settings"
    >
      <i class="fas fa-gear" aria-hidden="true"></i>
    </button>
    <button
      type="button"
      class="nav-mode-button"
      title={`Appearance: ${appearanceMode}`}
      on:click={cycleAppearanceMode}
    >
      <i
        class={`fas ${appearanceMode === "light"
          ? "fa-sun"
          : appearanceMode === "dark"
            ? "fa-moon"
            : "fa-desktop"}`}
        aria-hidden="true"
      ></i>
      <span>{appearanceMode}</span>
    </button>
    <div class="theme-menu-shell" bind:this={themeMenuEl}>
      <button
        type="button"
        class="nav-theme-button"
        on:click={toggleThemeMenu}
        title={`${themeStatusText} · ${activeEditorThemeName}`}
        aria-haspopup="dialog"
        aria-expanded={themeMenuOpen}
      >
        <i class="fas fa-palette" aria-hidden="true"></i>
      </button>

      {#if themeMenuOpen}
        <div class="theme-menu" role="dialog" aria-label="Theme settings">
          <div class="theme-menu-section">
            <div class="theme-menu-heading">
              <span class="theme-menu-label">Theme</span>
              <span class="theme-menu-meta">{themePref} mode</span>
            </div>
            <select
              value={activeEditorTheme}
              on:change={(event) => {
                setEditorTheme(
                  (event.currentTarget as HTMLSelectElement)
                    .value as BundledTheme,
                );
              }}
            >
              {#each availableEditorThemes as themeOption}
                <option value={themeOption.id}>{themeOption.displayName}</option>
              {/each}
            </select>
          </div>

          <p class="theme-menu-summary">
            Using <strong>{activeEditorThemeName}</strong> across the full {themePref} theme.
          </p>
        </div>
      {/if}
    </div>
    <div class="account-menu-shell" bind:this={accountMenuEl}>
      <button
        type="button"
        class="nav-icon"
        class:active={accountMenuOpen}
        title="Account"
        aria-haspopup="dialog"
        aria-expanded={accountMenuOpen}
        on:click={toggleAccountMenu}
      >
        <i class="fas fa-user" aria-hidden="true"></i>
      </button>

      {#if accountMenuOpen}
        <div class="account-menu" role="dialog" aria-label="Account summary">
          {#if sessionUser}
            <section class="account-summary-card">
              <div class="account-avatar">{accountInitials(sessionUser.name)}</div>
              <div class="account-summary-copy">
                <p class="eyebrow">Account</p>
                <h2>{sessionUser.name}</h2>
                <p class="account-summary-meta">
                  {sessionUser.guest ? "Guest session" : "Registered account"} · {accountPercentileLabel}
                </p>
              </div>
              <div class="account-elo-pill">
                <span>ELO</span>
                <strong>{sessionUser.elo}</strong>
              </div>
            </section>

            <section class="account-stat-grid">
              <article class="account-stat-card">
                <span class="eyebrow">Global Rank</span>
                <strong>{accountRankLabel}</strong>
                <small>{leaderboardTotalPlayers} players tracked</small>
              </article>
              <article class="account-stat-card">
                <span class="eyebrow">Solve Rate</span>
                <strong>{accountSolveRate === null ? "--" : `${accountSolveRate}%`}</strong>
                <small>{accountStats.matchesSolved}/{accountStats.matchesStarted} cleared</small>
              </article>
              <article class="account-stat-card">
                <span class="eyebrow">Ranked Wins</span>
                <strong>{accountRankedWinLabel}</strong>
                <small>finished ranked runs</small>
              </article>
            </section>

            <div class="account-content-grid">
              <section class="account-card">
                <div class="account-card-head">
                  <div>
                    <p class="eyebrow">Recent Runs</p>
                    <h3>Match activity</h3>
                  </div>
                  <span>{accountStats.recentRuns.length} tracked</span>
                </div>

                {#if accountStats.recentRuns.length === 0}
                  <p class="account-empty">Finish a match to start building your recent history.</p>
                {:else}
                  <div class="account-run-list">
                    {#each accountStats.recentRuns as run}
                      <article class="account-run-row">
                        <div>
                          <strong>{run.mode}</strong>
                          <p>{run.theme} · {run.difficulty}</p>
                        </div>
                        <div class="account-run-meta">
                          <span class:success-text={run.outcome === "solved"} class:error-text={run.outcome === "forfeit"}>
                            {run.outcome === "solved" ? "Solved" : "Forfeit"}
                          </span>
                          <span>{run.hidden_passed} hidden</span>
                          <span>{formatRatingDelta(run.rating_delta)} elo</span>
                          <span>{formatActivityTime(run.at)}</span>
                        </div>
                      </article>
                    {/each}
                  </div>
                {/if}
              </section>

              <section class="account-card">
                <div class="account-card-head">
                  <div>
                    <p class="eyebrow">Overview</p>
                    <h3>Current focus</h3>
                  </div>
                </div>

                <div class="account-overview-list">
                  <div class="account-overview-row">
                    <span>Appearance</span>
                    <strong>{appearanceMode === "system" ? `System · ${themePref}` : appearanceMode}</strong>
                  </div>
                  <div class="account-overview-row">
                    <span>Theme</span>
                    <strong>{activeEditorThemeName}</strong>
                  </div>
                  <div class="account-overview-row">
                    <span>Sample runs</span>
                    <strong>{accountStats.sampleRuns}</strong>
                  </div>
                  <div class="account-overview-row">
                    <span>Hints used</span>
                    <strong>{accountStats.hintsUsed}</strong>
                  </div>
                  <div class="account-overview-row">
                    <span>Submissions</span>
                    <strong>{accountStats.submissions}</strong>
                  </div>
                  <div class="account-overview-row">
                    <span>Live race</span>
                    <strong>{matchSummaryLabel}</strong>
                  </div>
                </div>
              </section>
            </div>

            <div class="account-actions">
              <button type="button" class="btn" on:click={toggleLeaderboardView}>
                Leaderboard
              </button>
              <button type="button" class="btn" on:click={showHome}>
                Home
              </button>
              <button
                type="button"
                class="btn"
                on:click={showArena}
                disabled={!hasActiveMatch || busy}
              >
                Resume Race
              </button>
              <button type="button" class="btn primary" on:click={logout} disabled={busy}>
                Sign Out
              </button>
            </div>

          {:else}
            <section class="account-card account-empty-card">
              <p class="eyebrow">Account</p>
              <h2>Sign in to track your profile</h2>
              <p class="account-empty">
                Your rank, solved matches, and recent activity will show up here once you have an active session.
              </p>
              <button
                type="button"
                class="btn primary"
                on:click={() => {
                  showHome();
                }}
              >
                Go to account setup
              </button>
            </section>
          {/if}
        </div>
      {/if}
    </div>
  </nav>
</header>
