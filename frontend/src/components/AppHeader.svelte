<script lang="ts">
  import { tick } from "svelte";
  import type { BundledTheme } from "shiki/bundle/web";
  import type {
    AccountStats,
    AppearanceMode,
    EditorFontFamily,
    EditorFontSize,
    KeybindMode,
    SessionUser,
    UiTheme,
    View,
  } from "../app-types";

  type QuickSettingAction = {
    id: string;
    label: string;
    description: string;
    icon: string;
    keywords: string;
    shortcut?: string;
    disabled?: boolean;
    run: () => void;
  };

  export let activeView: View = "home";
  export let appearanceMode: AppearanceMode = "light";
  export let themeStatusText = "";
  export let activeEditorThemeName = "";
  export let themePref: UiTheme = "light";
  export let activeEditorTheme: BundledTheme = "everforest-light";
  export let availableEditorThemes: Array<{ id: string; displayName: string }> = [];
  export let profileImageUrl = "";
  export let editorFontFamily: EditorFontFamily = "roboto-mono";
  export let editorFontFamilyOptions: Array<{ id: EditorFontFamily; label: string }> = [];
  export let editorFontSize: EditorFontSize = 14;
  export let keybindMode: KeybindMode = "normal";

  export let sessionUser: SessionUser | null = null;
  export let isAdmin = false;
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
  export let showAdmin: () => void = () => {};
  export let showSettings: () => void = () => {};
  export let setAppearanceMode: (mode: AppearanceMode) => void = () => {};
  export let cycleAppearanceMode: () => void = () => {};
  export let toggleThemeMenu: () => void = () => {};
  export let toggleAccountMenu: () => void = () => {};
  export let setEditorTheme: (themeId: BundledTheme) => void = () => {};
  export let setEditorFontFamily: (family: EditorFontFamily) => void = () => {};
  export let setEditorFontSize: (size: EditorFontSize) => void = () => {};
  export let setKeybindMode: (mode: KeybindMode) => void = () => {};
  export let resetThemePreferences: () => void = () => {};
  export let uploadProfileImage: (file: File) => void | Promise<void> = () => {};
  export let accountInitials: (name: string) => string = () => "EN";
  export let formatActivityTime: (timestamp: string) => string = () => "";
  export let formatRatingDelta: (value: number) => string = (value) => String(value);
  export let showArena: () => void = () => {};
  export let logout: () => void | Promise<void> = () => {};

  const quickFontSizeOptions: EditorFontSize[] = [12, 14, 16, 18];
  const quickAppearanceModes: AppearanceMode[] = ["system", "light", "dark"];

  let quickSettingsOpen = false;
  let quickSettingsQuery = "";
  let quickSettingsIndex = 0;
  let quickSettingsInputEl: HTMLInputElement | null = null;
  let quickSettingsActions: QuickSettingAction[] = [];
  let accountImageInputEl: HTMLInputElement | null = null;

  function closeQuickSettings(): void {
    quickSettingsOpen = false;
  }

  function openQuickSettings(): void {
    quickSettingsOpen = true;
    themeMenuOpen = false;
    accountMenuOpen = false;
    void tick().then(() => {
      quickSettingsInputEl?.focus();
      quickSettingsInputEl?.select();
    });
  }

  function runQuickSetting(action: QuickSettingAction): void {
    action.run();
    closeQuickSettings();
  }

  function quickAppearanceLabel(mode: AppearanceMode): string {
    if (mode === "system") {
      return "Follow system appearance";
    }
    return `Use ${mode} appearance`;
  }

  async function handleAccountImageChange(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      await uploadProfileImage(file);
    }
    input.value = "";
  }

  function handleQuickSettingsKeydown(event: KeyboardEvent): void {
    const usesCommandShortcut =
      (event.metaKey || event.ctrlKey) &&
      !event.altKey &&
      event.key.toLowerCase() === "k";

    if (usesCommandShortcut) {
      event.preventDefault();
      if (quickSettingsOpen) {
        closeQuickSettings();
      } else {
        openQuickSettings();
      }
      return;
    }

    if (!quickSettingsOpen) {
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeQuickSettings();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      quickSettingsIndex = quickSettingsActions.length === 0
        ? 0
        : (quickSettingsIndex + 1) % quickSettingsActions.length;
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      quickSettingsIndex = quickSettingsActions.length === 0
        ? 0
        : (quickSettingsIndex - 1 + quickSettingsActions.length) %
          quickSettingsActions.length;
      return;
    }

    if (event.key === "Enter" && quickSettingsActions[quickSettingsIndex]) {
      event.preventDefault();
      runQuickSetting(quickSettingsActions[quickSettingsIndex]);
    }
  }

  $: {
    const navigationActions: QuickSettingAction[] = [
      {
        id: "quick-play",
        label: "Go to play",
        description: hasActiveMatch ? "Return to the live arena or play home" : "Open the play view",
        icon: "fa-gamepad",
        keywords: "play arena home game",
        shortcut: "Ctrl/Cmd+K",
        run: showPlayView,
      },
      {
        id: "quick-leaderboard",
        label: "Open leaderboard",
        description: "Jump to the ranked ladder",
        icon: "fa-crown",
        keywords: "leaderboard ladder ranked crown",
        run: () => {
          if (activeView !== "leaderboard") {
            toggleLeaderboardView();
          } else {
            showPlayView();
          }
        },
      },
      {
        id: "quick-settings-view",
        label: "Open full settings",
        description: "Jump to the full settings workspace",
        icon: "fa-gear",
        keywords: "settings preferences workspace config",
        run: showSettings,
      },
      {
        id: "quick-resume",
        label: "Resume live match",
        description: matchSummaryLabel,
        icon: "fa-play",
        keywords: "resume active live match arena",
        disabled: !hasActiveMatch,
        run: showArena,
      },
    ];

    if (isAdmin) {
      navigationActions.push({
        id: "quick-admin",
        label: "Open admin dashboard",
        description: "Manage users, ELO, and live matches",
        icon: "fa-shield-halved",
        keywords: "admin dashboard moderation users elo matches",
        run: showAdmin,
      });
    }

    const appearanceActions = quickAppearanceModes.map((mode) => ({
      id: `quick-appearance-${mode}`,
      label: quickAppearanceLabel(mode),
      description:
        appearanceMode === mode
          ? "Currently active"
          : "Switch the full app appearance",
      icon:
        mode === "system"
          ? "fa-desktop"
          : mode === "light"
            ? "fa-sun"
            : "fa-moon",
      keywords: `appearance theme color mode ${mode}`,
      run: () => setAppearanceMode(mode),
    }));

    const themeActions: QuickSettingAction[] = availableEditorThemes.map((themeOption) => ({
      id: `quick-theme-${themeOption.id}`,
      label: `Theme: ${themeOption.displayName}`,
      description:
        activeEditorTheme === themeOption.id
          ? `Active ${themePref} palette`
          : `Apply this ${themePref} palette`,
      icon: "fa-palette",
      keywords: `theme palette ${themePref} ${themeOption.displayName}`,
      run: () => setEditorTheme(themeOption.id as BundledTheme),
    }));

    const fontActions: QuickSettingAction[] = editorFontFamilyOptions.map((fontOption) => ({
      id: `quick-font-${fontOption.id}`,
      label: `Font: ${fontOption.label}`,
      description:
        editorFontFamily === fontOption.id
          ? "Currently active across the app"
          : "Apply this font across the UI and editor",
      icon: "fa-font",
      keywords: `font typography editor ${fontOption.label}`,
      run: () => setEditorFontFamily(fontOption.id),
    }));

    const fontSizeActions: QuickSettingAction[] = quickFontSizeOptions.map((size) => ({
      id: `quick-font-size-${size}`,
      label: `Font size: ${size}px`,
      description:
        editorFontSize === size
          ? "Currently active"
          : "Update the editor scale",
      icon: "fa-text-height",
      keywords: `font size text scale ${size}`,
      run: () => setEditorFontSize(size),
    }));

    const editorModeActions: QuickSettingAction[] = [
      {
        id: "quick-keybind-vim-toggle",
        label: keybindMode === "vim" ? "Disable Vim mode" : "Enable Vim mode",
        description:
          keybindMode === "vim"
            ? "Currently using Vim keybinds. Switch back to normal typing."
            : "Toggle Vim keybinds on for the editor.",
        icon: "fa-keyboard",
        keywords: `editor keybind vim modal normal custom ${keybindMode}`,
        run: () => setKeybindMode(keybindMode === "vim" ? "normal" : "vim"),
      },
    ];

    const utilityActions: QuickSettingAction[] = [
      {
        id: "quick-reset-theme",
        label: "Reset theme defaults",
        description: "Restore appearance, theme palette, and typography defaults",
        icon: "fa-rotate-left",
        keywords: "reset defaults theme appearance font typography",
        run: resetThemePreferences,
      },
      {
        id: "quick-sign-out",
        label: "Sign out",
        description: sessionUser ? `End session for ${sessionUser.name}` : "No active session",
        icon: "fa-right-from-bracket",
        keywords: "logout sign out account session",
        disabled: !sessionUser,
        run: () => {
          void logout();
        },
      },
    ];

    const allActions = [
      ...navigationActions,
      ...appearanceActions,
      ...themeActions,
      ...fontActions,
      ...fontSizeActions,
      ...editorModeActions,
      ...utilityActions,
    ];

    const searchNeedle = quickSettingsQuery.trim().toLowerCase();
    quickSettingsActions = searchNeedle.length === 0
      ? allActions
      : allActions.filter((action) => {
          const haystack = `${action.label} ${action.description} ${action.keywords}`
            .toLowerCase();
          return searchNeedle.split(/\s+/).every((term) => haystack.includes(term));
        });

    if (quickSettingsIndex >= quickSettingsActions.length) {
      quickSettingsIndex = Math.max(0, quickSettingsActions.length - 1);
    }
  }
</script>

<svelte:window on:keydown={handleQuickSettingsKeydown} />

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
    {#if isAdmin}
      <button
        type="button"
        class="nav-icon"
        class:active={activeView === "admin"}
        on:click={showAdmin}
        title="Admin"
      >
        <i class="fas fa-shield-halved" aria-hidden="true"></i>
      </button>
    {/if}
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
              <div class="account-avatar-shell">
                <div class="account-avatar">
                  {#if profileImageUrl}
                    <img
                      class="avatar-image"
                      src={profileImageUrl}
                      alt={`${sessionUser.name} profile photo`}
                    />
                  {:else}
                    {accountInitials(sessionUser.name)}
                  {/if}
                </div>
                <input
                  bind:this={accountImageInputEl}
                  class="account-avatar-input"
                  type="file"
                  accept="image/*"
                  on:change={(event) => void handleAccountImageChange(event)}
                />
                <button
                  type="button"
                  class="account-avatar-button"
                  on:click={() => accountImageInputEl?.click()}
                  aria-label="Upload profile photo"
                >
                  <i class="fas fa-plus" aria-hidden="true"></i>
                </button>
              </div>
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

{#if quickSettingsOpen}
  <button
    type="button"
    class="quick-settings-backdrop"
    aria-label="Close quick settings"
    on:click={closeQuickSettings}
  ></button>
  <div class="quick-settings-panel" role="dialog" aria-modal="true" aria-label="Quick settings">
    <div class="quick-settings-search">
      <i class="fas fa-angle-right" aria-hidden="true"></i>
      <input
        bind:this={quickSettingsInputEl}
        bind:value={quickSettingsQuery}
        type="text"
        placeholder="Search settings, theme, font, or view"
        autocomplete="off"
        spellcheck="false"
      />
      <span class="quick-settings-hint">esc</span>
    </div>

    <div class="quick-settings-results">
      {#if quickSettingsActions.length === 0}
        <p class="quick-settings-empty">No quick settings matched that search.</p>
      {:else}
        {#each quickSettingsActions as action, index (action.id)}
          <button
            type="button"
            class="quick-settings-item"
            class:active={index === quickSettingsIndex}
            on:mouseenter={() => {
              quickSettingsIndex = index;
            }}
            on:click={() => runQuickSetting(action)}
            disabled={action.disabled}
          >
            <span class="quick-settings-item-copy">
              <span class="quick-settings-item-label">
                <i class={`fas ${action.icon}`} aria-hidden="true"></i>
                <strong>{action.label}</strong>
              </span>
              <small>{action.description}</small>
            </span>
            {#if action.shortcut}
              <span class="quick-settings-item-shortcut">{action.shortcut}</span>
            {/if}
          </button>
        {/each}
      {/if}
    </div>
  </div>
{/if}
