<script lang="ts">
  import type {
    AuthMode,
    Difficulty,
    LiveStatusTone,
    MatchPayload,
    Mode,
    PartyPayload,
    RankedQueuePayload,
    SessionUser,
  } from "../app-types";

  export let sessionUser: SessionUser | null = null;
  export let busy = false;
  export let authMode: AuthMode = "register";
  export let authName = "";
  export let authPassword = "";
  export let mode: Mode = "zen";
  export let difficulty: Difficulty = "easy";
  export let selectedTheme = "";
  export let timeLimitSeconds = 900;
  export let partyLimit = 4;
  export let joinCodeInput = "";
  export let party: PartyPayload | null = null;
  export let rankedQueue: RankedQueuePayload | null = null;
  export let match: MatchPayload | null = null;
  export let timerText = "00:00";
  export let themes: string[] = [];
  export let modeOptions: Mode[] = [];
  export let difficultyOptions: Difficulty[] = [];
  export let isPartyMode = false;
  export let isRankedMode = false;
  export let isPartyLeader = false;
  export let canEditPartySetup = true;
  export let liveStatusText = "Idle";
  export let liveStatusTone: LiveStatusTone = "neutral";
  export let notice = "";
  export let error = "";
  export let partyLimitMin = 2;
  export let partyLimitMax = 16;

  export let clearFlash: () => void = () => {};
  export let startRace: (nextMode: Mode) => void | Promise<void> = () => {};
  export let authenticate: (nextMode: AuthMode) => void | Promise<void> = () => {};
  export let updatePartySetup: () => void | Promise<void> = () => {};
  export let updatePartyLimit: () => void | Promise<void> = () => {};
  export let copyPartyInvite: () => void | Promise<void> = () => {};
  export let refreshPartyLobby: () => void | Promise<void> = () => {};
  export let joinPartyLobby: () => void | Promise<void> = () => {};
  export let kickPartyMember: (memberId: string) => void | Promise<void> = () => {};
  export let clearPartyLobby: () => void | Promise<void> = () => {};
  export let refreshRankedQueue: () => void | Promise<void> = () => {};
  export let leaveRankedQueue: () => void | Promise<void> = () => {};
  export let launchConfiguredMatch: () => void | Promise<void> = () => {};
  export let resumeRace: () => void | Promise<void> = () => {};
  export let logout: () => void | Promise<void> = () => {};
  export let normalizePartyCode: (raw: string) => string = (raw) => raw;

  $: resumableMatch = match && !match.finished && !match.locked ? match : null;
</script>

<main id="home-view">
  <div class="hero-text">
    Infer the hidden rule. Write the Python snippet.<br />
    <span>Defeat your opponents.</span>
  </div>

  {#if resumableMatch}
    <button
      type="button"
      class="resume-spotlight"
      on:click={resumeRace}
      disabled={!sessionUser || busy}
    >
      <span class="eyebrow">Match in progress</span>
      <h3>Resume your race</h3>
      <p>
        {resumableMatch.mode.toUpperCase()} | {resumableMatch.theme} | {resumableMatch.difficulty.toUpperCase()} | {timerText}
        left
      </p>
    </button>
  {:else}
    <div class="mode-selector" role="group" aria-label="Play mode">
      <button
        type="button"
        class="mode-card"
        on:click={() => startRace("zen")}
        disabled={!sessionUser || busy}
      >
        <i class="fas fa-mountain" aria-hidden="true"></i>
        <h3>Zen Mode</h3>
        <p>Solo play. No rating. Infinite time.</p>
      </button>

      <button
        type="button"
        class="mode-card"
        on:click={() => startRace("casual")}
        disabled={!sessionUser || busy}
      >
        <i class="fas fa-user-friends" aria-hidden="true"></i>
        <h3>Casual Party</h3>
        <p>Play with friends via link. Custom rules.</p>
      </button>

      <button
        type="button"
        class="mode-card"
        on:click={() => startRace("ranked")}
        disabled={!sessionUser || busy}
      >
        <i class="fas fa-trophy" aria-hidden="true"></i>
        <h3>Ranked</h3>
        <p>Random theme. 1 hour limit. ELO rating.</p>
      </button>
    </div>
  {/if}

  <section class="home-panels">
    {#if !sessionUser}
      <article class="home-card auth-card">
        <h2>Account</h2>

        <div class="segmented auth-switch">
          <button
            type="button"
            class:active={authMode === "register"}
            on:click={() => {
              authMode = "register";
              clearFlash();
            }}
          >
            Create account
          </button>
          <button
            type="button"
            class:active={authMode === "login"}
            on:click={() => {
              authMode = "login";
              clearFlash();
            }}
          >
            Sign in
          </button>
        </div>

        <label>
          <span>Display name</span>
          <input
            bind:value={authName}
            maxlength="24"
            autocomplete="username"
          />
        </label>

        <label>
          <span>Password</span>
          <input
            type="password"
            bind:value={authPassword}
            minlength="6"
            autocomplete={authMode === "login"
              ? "current-password"
              : "new-password"}
          />
        </label>

        <button
          type="button"
          class="btn primary wide"
          on:click={() => authenticate(authMode)}
          disabled={busy ||
            authName.trim().length === 0 ||
            authPassword.length < 6}
        >
          {authMode === "register" ? "Create Account" : "Sign In"}
        </button>
      </article>
    {:else}
      <article class="home-card setup-card">
        <div class="setup-head">
          <h2>Match Setup</h2>
          <p>{sessionUser.name} | ELO {sessionUser.elo}</p>
        </div>

        <div class="field-grid">
          <label>
            <span>Mode</span>
            <select bind:value={mode} disabled={!!party || !!rankedQueue || busy}>
              {#each modeOptions as option}
                <option value={option}>{option.toUpperCase()}</option>
              {/each}
            </select>
          </label>

          <label>
            <span>Puzzle theme</span>
            <select
              bind:value={selectedTheme}
              disabled={mode === "ranked" || !canEditPartySetup || busy}
            >
              {#each themes as theme}
                <option value={theme}>{theme}</option>
              {/each}
            </select>
          </label>

          <label>
            <span>Difficulty</span>
            <select
              bind:value={difficulty}
              disabled={mode === "ranked" || !canEditPartySetup || busy}
            >
              {#each difficultyOptions as option}
                <option value={option}>{option.toUpperCase()}</option>
              {/each}
            </select>
          </label>

          <label>
            <span>Time (seconds)</span>
            <input
              type="number"
              bind:value={timeLimitSeconds}
              min="60"
              max="7200"
              disabled={mode === "ranked" || !canEditPartySetup || busy}
            />
          </label>

          <label>
            <span>Party limit</span>
            <input
              type="number"
              bind:value={partyLimit}
              min={isPartyMode ? partyLimitMin : 1}
              max={isPartyMode ? partyLimitMax : 1}
              disabled={!isPartyMode || (!isPartyLeader && !!party) || busy}
            />
          </label>

        </div>

        {#if isPartyMode}
          <div class="party-lobby">
            <div class="party-lobby-head">
              <h3>Party Lobby</h3>
              <div class="party-live-head-actions">
                <span class={`live-status-badge ${liveStatusTone}`}>
                  <i class="fas fa-signal" aria-hidden="true"></i> {liveStatusText}
                </span>
                {#if party}
                  <button
                    type="button"
                    class="btn"
                    on:click={refreshPartyLobby}
                    disabled={busy}
                  >
                    <i class="fas fa-rotate-right" aria-hidden="true"></i> Refresh
                  </button>
                {/if}
              </div>
            </div>

            {#if party}
              <div class="party-code-row mono">
                <span class="eyebrow">Join code</span>
                <strong>{party.join_code}</strong>
                <button
                  type="button"
                  class="btn"
                  on:click={copyPartyInvite}
                  disabled={busy}
                >
                  <i class="fas fa-copy" aria-hidden="true"></i> Copy code
                </button>
              </div>

              {#if isPartyLeader}
                <div class="party-limit-row">
                  <span>
                    {party.members.length}/{party.member_limit} members
                  </span>
                  <div class="party-leader-actions">
                    {#if party.mode === "casual"}
                      <button
                        type="button"
                        class="btn"
                        on:click={updatePartySetup}
                        disabled={busy}
                      >
                        Update setup
                      </button>
                    {/if}
                    <button
                      type="button"
                      class="btn"
                      on:click={updatePartyLimit}
                      disabled={busy}
                    >
                      Update limit
                    </button>
                  </div>
                </div>
              {:else}
                <p class="party-note">
                  Waiting for the leader to update settings and start the match.
                </p>
              {/if}

              <div class="party-members">
                {#each party.members as member}
                  <article class="party-member-row">
                    <span class="mono">
                      {member.name}
                      {#if member.id === party.leader_id}
                        <em>(leader)</em>
                      {/if}
                    </span>
                    {#if isPartyLeader && member.id !== party.leader_id}
                      <button
                        type="button"
                        class="btn"
                        on:click={() => void kickPartyMember(member.id)}
                        disabled={busy}
                      >
                        Kick
                      </button>
                    {/if}
                  </article>
                {/each}
              </div>
            {:else}
              <div class="party-join-row">
                <label>
                  <span>Join code</span>
                  <input
                    value={joinCodeInput}
                    maxlength="6"
                    placeholder="ABC123"
                    on:input={(event) => {
                      joinCodeInput = normalizePartyCode(
                        (event.currentTarget as HTMLInputElement).value,
                      );
                    }}
                  />
                </label>
                <button
                  type="button"
                  class="btn"
                  on:click={joinPartyLobby}
                  disabled={busy || normalizePartyCode(joinCodeInput).length !== 6}
                >
                  Join Party
                </button>
              </div>
            {/if}
          </div>
        {:else if isRankedMode}
          <div class="party-lobby">
            <div class="party-lobby-head">
              <h3>Ranked Queue</h3>
              <div class="party-live-head-actions">
                <span class={`live-status-badge ${liveStatusTone}`}>
                  <i class="fas fa-signal" aria-hidden="true"></i> {liveStatusText}
                </span>
                {#if rankedQueue}
                  <button
                    type="button"
                    class="btn"
                    on:click={refreshRankedQueue}
                    disabled={busy}
                  >
                    <i class="fas fa-rotate-right" aria-hidden="true"></i> Refresh
                  </button>
                {/if}
              </div>
            </div>

            {#if rankedQueue}
              <div class="party-code-row mono">
                <span class="eyebrow">Current search</span>
                <strong>
                  ELO {rankedQueue.queued_elo} +/- {rankedQueue.search_range}
                </strong>
              </div>

              <p class="party-note">
                Searching for an opponent. {rankedQueue.queued_players} player{rankedQueue.queued_players === 1 ? "" : "s"} currently waiting.
              </p>
            {:else}
              <p class="party-note">
                Ranked uses live matchmaking. Join the queue to get paired with a nearby ELO opponent in a 1v1 match.
              </p>
            {/if}
          </div>
        {/if}

        <div class="home-actions">
          <button
            type="button"
            class="btn primary"
            on:click={launchConfiguredMatch}
            disabled={busy || (isPartyMode && !!party && !isPartyLeader) || (isRankedMode && !!rankedQueue)}
          >
            {#if mode === "zen"}
              {match ? "Restart Match" : "Start Match"}
            {:else if isRankedMode && rankedQueue}
              Searching Matchmaking
            {:else if !party}
              {isRankedMode ? "Join Ranked Queue" : "Create Party"}
            {:else if !isPartyLeader}
              Waiting for Leader
            {:else}
              Start Party Match
            {/if}
          </button>

          <button
            type="button"
            class="btn resume"
            on:click={resumeRace}
            disabled={!resumableMatch || busy}
          >
            Resume Race
          </button>

          {#if party}
            <button
              type="button"
              class="btn"
              on:click={clearPartyLobby}
              disabled={busy}
            >
              Close Lobby
            </button>
          {:else if rankedQueue}
            <button
              type="button"
              class="btn"
              on:click={leaveRankedQueue}
              disabled={busy}
            >
              Leave Queue
            </button>
          {/if}

          <button
            type="button"
            class="btn"
            on:click={logout}
            disabled={busy}
          >
            Sign Out
          </button>
        </div>
      </article>
    {/if}
  </section>

  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error}
    <p class="flash error">{error}</p>
  {/if}
</main>
