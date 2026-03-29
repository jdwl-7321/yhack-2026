<script lang="ts">
  import type {
    AdminMatch,
    AdminPuzzleTemplate,
    Difficulty,
    SessionUser,
  } from "../app-types";

  export let sessionUser: SessionUser | null = null;
  export let isAdmin = false;
  export let busy = false;
  export let adminUsers: SessionUser[] = [];
  export let adminMatches: AdminMatch[] = [];
  export let adminPuzzleTemplates: AdminPuzzleTemplate[] = [];
  export let missingPuzzleTemplateKeys: string[] = [];
  export let notice = "";
  export let error = "";

  export let formatDuration: (seconds: number) => string = (seconds) => `${seconds}`;
  export let refreshAdminDashboard: () => void | Promise<void> = () => {};
  export let resetAllElos: () => void | Promise<void> = () => {};
  export let updateUserElo: (
    userId: string,
    elo: number,
  ) => void | Promise<void> = () => {};
  export let deleteUserAccount: (userId: string) => void | Promise<void> = () => {};
  export let cancelActiveMatch: (matchId: string) => void | Promise<void> = () => {};
  export let createPuzzleTemplate: (
    templateKey: string,
  ) => void | Promise<void> = () => {};
  export let updatePuzzleTemplate: (
    template: AdminPuzzleTemplate,
  ) => void | Promise<void> = () => {};
  export let deletePuzzleTemplate: (
    templateKey: string,
  ) => void | Promise<void> = () => {};

  let draftEloByUser: Record<string, string> = {};
  let selectedMissingTemplateKey = "";
  let localError = "";
  const themeOptions = ["Cryptography", "Algorithms", "Numeric"];
  const difficultyOptions: Difficulty[] = ["easy", "medium", "hard", "expert"];

  $: if (!missingPuzzleTemplateKeys.includes(selectedMissingTemplateKey)) {
    selectedMissingTemplateKey = missingPuzzleTemplateKeys[0] ?? "";
  }

  function isDifficulty(value: string): value is Difficulty {
    return difficultyOptions.includes(value as Difficulty);
  }

  function eloDraft(user: SessionUser): string {
    return draftEloByUser[user.id] ?? String(user.elo);
  }

  function setEloDraft(userId: string, value: string): void {
    draftEloByUser = { ...draftEloByUser, [userId]: value };
  }

  async function submitUserElo(user: SessionUser): Promise<void> {
    const parsed = Number.parseInt(eloDraft(user), 10);
    if (!Number.isInteger(parsed) || parsed < 0) {
      localError = "ELO must be a non-negative integer.";
      return;
    }
    localError = "";
    await updateUserElo(user.id, parsed);
    setEloDraft(user.id, String(parsed));
  }

  async function confirmDelete(user: SessionUser): Promise<void> {
    const confirmed = window.confirm(
      `Delete account ${user.name}? Active matches for this user will be cancelled.`,
    );
    if (!confirmed) {
      return;
    }
    localError = "";
    await deleteUserAccount(user.id);
  }

  async function confirmCancelMatch(matchId: string): Promise<void> {
    const confirmed = window.confirm(
      `Cancel active match ${matchId}? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    localError = "";
    await cancelActiveMatch(matchId);
  }

  async function restoreMissingPuzzleTemplate(): Promise<void> {
    if (!selectedMissingTemplateKey) {
      localError = "Select a template key to restore.";
      return;
    }
    localError = "";
    await createPuzzleTemplate(selectedMissingTemplateKey);
  }

  async function submitPuzzleUpdate(
    template: AdminPuzzleTemplate,
    event: SubmitEvent,
  ): Promise<void> {
    const form = event.currentTarget;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const formData = new FormData(form);
    const theme = String(formData.get("theme") ?? "").trim();
    const difficultyRaw = String(formData.get("difficulty") ?? "").trim();
    const prompt = String(formData.get("prompt") ?? "").trim();
    const hintLevel1 = String(formData.get("hint_level_1") ?? "").trim();
    const hintLevel2 = String(formData.get("hint_level_2") ?? "").trim();
    const hintLevel3 = String(formData.get("hint_level_3") ?? "").trim();
    const sourceCode = String(formData.get("source_code") ?? "");
    const enabled = formData.get("enabled") === "on";

    if (!theme) {
      localError = "Theme is required.";
      return;
    }
    if (!isDifficulty(difficultyRaw)) {
      localError = "Difficulty must be easy, medium, hard, or expert.";
      return;
    }
    if (!prompt || !hintLevel1 || !hintLevel2 || !hintLevel3) {
      localError = "Prompt and all hint fields are required.";
      return;
    }
    if (!sourceCode.trim()) {
      localError = "Puzzle source code is required.";
      return;
    }

    localError = "";
    await updatePuzzleTemplate({
      template_key: template.template_key,
      theme,
      difficulty: difficultyRaw,
      prompt,
      hint_level_1: hintLevel1,
      hint_level_2: hintLevel2,
      hint_level_3: hintLevel3,
      enabled,
      source_path: template.source_path,
      source_code: sourceCode,
    });
  }

  async function confirmDeletePuzzle(template: AdminPuzzleTemplate): Promise<void> {
    const confirmed = window.confirm(
      `Delete puzzle template ${template.template_key}? You can restore it later from hardcoded templates.`,
    );
    if (!confirmed) {
      return;
    }
    localError = "";
    await deletePuzzleTemplate(template.template_key);
  }
</script>

<main id="admin-view">
  {#if !sessionUser}
    <section class="admin-card">
      <h1>Admin Dashboard</h1>
      <p class="admin-muted">Sign in to access admin controls.</p>
    </section>
  {:else if !isAdmin}
    <section class="admin-card">
      <h1>Admin Dashboard</h1>
      <p class="admin-muted">Access denied. This account is not configured as admin.</p>
    </section>
  {:else}
    <section class="admin-hero admin-card">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Admin Dashboard</h1>
        <p class="admin-muted">Manage accounts, ELO values, and active matches.</p>
      </div>
      <div class="admin-actions">
        <button type="button" class="btn" on:click={() => void refreshAdminDashboard()} disabled={busy}>
          Refresh
        </button>
        <button type="button" class="btn" on:click={() => void resetAllElos()} disabled={busy}>
          Reset all ELO to 1000
        </button>
      </div>
    </section>

    <section class="admin-layout">
      <article class="admin-card">
        <div class="admin-card-head">
          <h2>Players</h2>
          <span>{adminUsers.length} total</span>
        </div>

        <div class="admin-users-grid">
          <div class="admin-users-head">
            <span>Player</span>
            <span>Current ELO</span>
            <span>Update ELO</span>
            <span>Delete</span>
          </div>
          {#each adminUsers as user}
            <div class="admin-users-row">
              <div class="admin-player-cell">
                <strong>{user.name}</strong>
                <small>{user.id}</small>
              </div>
              <span>{user.elo}</span>
              <div class="admin-elo-actions">
                <input
                  type="number"
                  min="0"
                  value={eloDraft(user)}
                  on:input={(event) => {
                    setEloDraft(user.id, (event.currentTarget as HTMLInputElement).value);
                  }}
                  disabled={busy}
                />
                <button
                  type="button"
                  class="btn"
                  on:click={() => void submitUserElo(user)}
                  disabled={busy}
                >
                  Set
                </button>
              </div>
              <button
                type="button"
                class="btn"
                on:click={() => void confirmDelete(user)}
                disabled={busy || user.id === sessionUser.id}
              >
                Delete
              </button>
            </div>
          {/each}
        </div>
      </article>

      <article class="admin-card">
        <div class="admin-card-head">
          <h2>Active Matches</h2>
          <span>{adminMatches.length} live</span>
        </div>

        {#if adminMatches.length === 0}
          <p class="admin-muted">No active matches right now.</p>
        {:else}
          <div class="admin-match-list">
            {#each adminMatches as match}
              <section class="admin-match-row">
                <div class="admin-match-copy">
                  <strong>{match.match_id}</strong>
                  <p>
                    {match.mode.toUpperCase()} · {match.theme} · {match.difficulty.toUpperCase()} ·
                    {formatDuration(match.time_limit_seconds)}
                  </p>
                  <p class="admin-muted">
                    Players: {match.players.map((player) => player.name).join(", ")}
                  </p>
                </div>
                <button
                  type="button"
                  class="btn"
                  on:click={() => void confirmCancelMatch(match.match_id)}
                  disabled={busy}
                >
                  Cancel Match
                </button>
              </section>
            {/each}
          </div>
        {/if}
      </article>

      <article class="admin-card">
        <div class="admin-card-head">
          <h2>Puzzle Templates</h2>
          <span>{adminPuzzleTemplates.length} configured</span>
        </div>

        {#if missingPuzzleTemplateKeys.length > 0}
          <section class="admin-puzzle-restore">
            <div>
              <strong>Restore hardcoded template</strong>
              <p class="admin-muted">
                Recreate a deleted hardcoded template with its default prompt and hints.
              </p>
            </div>
            <div class="admin-puzzle-restore-actions">
              <select
                bind:value={selectedMissingTemplateKey}
                disabled={busy || missingPuzzleTemplateKeys.length === 0}
              >
                {#each missingPuzzleTemplateKeys as templateKey}
                  <option value={templateKey}>{templateKey}</option>
                {/each}
              </select>
              <button
                type="button"
                class="btn"
                disabled={busy || !selectedMissingTemplateKey}
                on:click={() => void restoreMissingPuzzleTemplate()}
              >
                Restore
              </button>
            </div>
          </section>
        {/if}

        {#if adminPuzzleTemplates.length === 0}
          <p class="admin-muted">No puzzle templates configured.</p>
        {:else}
          <div class="admin-puzzle-list">
            {#each adminPuzzleTemplates as template}
              <form
                class="admin-puzzle-form"
                on:submit|preventDefault={(event) => void submitPuzzleUpdate(template, event)}
              >
                <div class="admin-puzzle-head">
                  <div>
                    <strong>{template.template_key}</strong>
                    <p class="admin-muted">{template.theme} · {template.difficulty.toUpperCase()}</p>
                    <p class="admin-muted">File: <code>{template.source_path}</code></p>
                  </div>
                  <label class="admin-toggle">
                    <input
                      type="checkbox"
                      name="enabled"
                      checked={template.enabled}
                      disabled={busy}
                    />
                    <span>Enabled</span>
                  </label>
                </div>

                <div class="admin-puzzle-grid">
                  <label>
                    Theme
                    <select name="theme" disabled={busy} value={template.theme}>
                      {#if !themeOptions.includes(template.theme)}
                        <option value={template.theme}>{template.theme}</option>
                      {/if}
                      {#each themeOptions as themeOption}
                        <option value={themeOption}>{themeOption}</option>
                      {/each}
                    </select>
                  </label>

                  <label>
                    Difficulty
                    <select name="difficulty" disabled={busy} value={template.difficulty}>
                      {#each difficultyOptions as difficultyOption}
                        <option value={difficultyOption}>{difficultyOption}</option>
                      {/each}
                    </select>
                  </label>
                </div>

                <label>
                  Prompt
                  <textarea name="prompt" rows="2" disabled={busy}>{template.prompt}</textarea>
                </label>

                <div class="admin-puzzle-grid admin-puzzle-hints">
                  <label>
                    Hint 1
                    <textarea
                      name="hint_level_1"
                      rows="2"
                      disabled={busy}
                    >{template.hint_level_1}</textarea>
                  </label>
                  <label>
                    Hint 2
                    <textarea
                      name="hint_level_2"
                      rows="2"
                      disabled={busy}
                    >{template.hint_level_2}</textarea>
                  </label>
                  <label>
                    Hint 3
                    <textarea
                      name="hint_level_3"
                      rows="2"
                      disabled={busy}
                    >{template.hint_level_3}</textarea>
                  </label>
                </div>

                <label>
                  Puzzle Source (Python)
                  <textarea
                    name="source_code"
                    class="admin-puzzle-source"
                    rows="14"
                    disabled={busy}
                  >{template.source_code}</textarea>
                </label>

                <div class="admin-puzzle-actions">
                  <button type="submit" class="btn" disabled={busy}>Save Template</button>
                  <button
                    type="button"
                    class="btn"
                    disabled={busy}
                    on:click={() => void confirmDeletePuzzle(template)}
                  >
                    Delete Template
                  </button>
                </div>
              </form>
            {/each}
          </div>
        {/if}
      </article>
    </section>
  {/if}

  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error || localError}
    <p class="flash error">{error || localError}</p>
  {/if}
</main>
