<script lang="ts">
  import { basicSetup, EditorView } from "codemirror";
  import { EditorState } from "@codemirror/state";
  import { python as cmPython } from "@codemirror/lang-python";
  import {
    HighlightStyle,
    syntaxHighlighting,
  } from "@codemirror/language";
  import { tags } from "@lezer/highlight";
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
    theme: string,
    difficulty: Difficulty,
  ) => void | Promise<void> = () => {};
  export let updatePuzzleTemplate: (
    template: AdminPuzzleTemplate,
  ) => void | Promise<void> = () => {};
  export let deletePuzzleTemplate: (templateKey: string) => void | Promise<void> = () => {};

  type TemplateDifficultyFilter = "all" | Difficulty;

  let draftEloByUser: Record<string, string> = {};
  let localError = "";
  let puzzleFilterQuery = "";
  let puzzleFilterTheme = "all";
  let puzzleFilterDifficulty: TemplateDifficultyFilter = "all";
  let newTemplateKey = "";
  let newTemplateTheme = "Algorithms";
  let newTemplateDifficulty: Difficulty = "easy";
  let openTemplateKeys = new Set<string>();
  const sourceEditorViews = new Map<string, EditorView>();

  const sourceHighlightStyle = HighlightStyle.define([
    {
      tag: [
        tags.keyword,
        tags.controlKeyword,
        tags.definitionKeyword,
        tags.modifier,
        tags.operatorKeyword,
      ],
      color: "var(--editor-keyword)",
    },
    {
      tag: [
        tags.string,
        tags.special(tags.string),
        tags.regexp,
        tags.character,
      ],
      color: "var(--editor-string)",
    },
    {
      tag: [tags.comment, tags.lineComment, tags.blockComment],
      color: "var(--editor-comment)",
    },
    {
      tag: [
        tags.number,
        tags.integer,
        tags.float,
        tags.bool,
        tags.null,
      ],
      color: "var(--editor-number)",
    },
    {
      tag: [
        tags.function(tags.variableName),
        tags.function(tags.propertyName),
        tags.labelName,
      ],
      color: "var(--editor-function)",
    },
  ]);

  const sourceEditorTheme = EditorView.theme({
    "&": {
      height: "100%",
      backgroundColor: "var(--editor-bg)",
      color: "var(--editor-text)",
    },
    ".cm-scroller": {
      fontFamily: "var(--editor-font-family)",
      fontSize: "var(--editor-font-size)",
      lineHeight: "1.5",
      overflow: "auto",
    },
    ".cm-gutters": {
      backgroundColor: "var(--editor-bg)",
      color: "var(--sub-color)",
      borderRight: "1px solid color-mix(in srgb, var(--sub-color) 35%, transparent)",
    },
    ".cm-activeLineGutter, .cm-activeLine": {
      backgroundColor: "color-mix(in srgb, var(--main-color) 8%, transparent)",
    },
    ".cm-cursor": {
      borderLeftColor: "var(--theme-accent)",
    },
    ".cm-selectionBackground, .cm-content ::selection": {
      backgroundColor: "var(--editor-selection)",
    },
    ".cm-focused": {
      outline: "none",
    },
  });

  type SourceEditorBinding = {
    templateKey: string;
    sourceCode: string;
  };

  $: availableTemplateThemes = Array.from(
    new Set(adminPuzzleTemplates.map((template) => template.theme)),
  ).sort((left, right) => left.localeCompare(right));

  $: filteredPuzzleTemplates = adminPuzzleTemplates.filter((template) => {
    if (puzzleFilterTheme !== "all" && template.theme !== puzzleFilterTheme) {
      return false;
    }
    if (
      puzzleFilterDifficulty !== "all" &&
      template.difficulty !== puzzleFilterDifficulty
    ) {
      return false;
    }

    const query = puzzleFilterQuery.trim().toLowerCase();
    if (!query) {
      return true;
    }

    const searchableText = [
      template.template_key,
      template.theme,
      template.difficulty,
      template.source_path,
      template.source_code,
    ]
      .join("\n")
      .toLowerCase();
    return searchableText.includes(query);
  });

  function sourceEditorHost(node: HTMLDivElement, binding: SourceEditorBinding) {
    let current = binding;

    const view = new EditorView({
      state: EditorState.create({
        doc: binding.sourceCode,
        extensions: [
          basicSetup,
          cmPython(),
          syntaxHighlighting(sourceHighlightStyle),
          sourceEditorTheme,
        ],
      }),
      parent: node,
    });
    sourceEditorViews.set(binding.templateKey, view);

    return {
      update(next: SourceEditorBinding) {
        if (next.templateKey !== current.templateKey) {
          sourceEditorViews.delete(current.templateKey);
          sourceEditorViews.set(next.templateKey, view);
        }

        const currentDoc = view.state.doc.toString();
        if (next.sourceCode !== currentDoc) {
          view.dispatch({
            changes: {
              from: 0,
              to: currentDoc.length,
              insert: next.sourceCode,
            },
          });
        }
        current = next;
      },
      destroy() {
        sourceEditorViews.delete(current.templateKey);
        view.destroy();
      },
    };
  }

  function resetPuzzleFilters(): void {
    puzzleFilterQuery = "";
    puzzleFilterTheme = "all";
    puzzleFilterDifficulty = "all";
  }

  async function submitCreatePuzzleTemplate(): Promise<void> {
    const templateKey = newTemplateKey
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
    if (!templateKey) {
      localError = "Template key is required.";
      return;
    }
    localError = "";
    await createPuzzleTemplate(templateKey, newTemplateTheme, newTemplateDifficulty);
    newTemplateKey = "";
    openTemplateKeys = new Set<string>([templateKey]);
  }

  function expandFilteredTemplates(): void {
    openTemplateKeys = new Set(filteredPuzzleTemplates.map((template) => template.template_key));
  }

  function collapseAllTemplates(): void {
    openTemplateKeys = new Set<string>();
  }

  function syncTemplateOpenState(templateKey: string, event: Event): void {
    const details = event.currentTarget;
    if (!(details instanceof HTMLDetailsElement)) {
      return;
    }

    const next = new Set(openTemplateKeys);
    if (details.open) {
      next.add(templateKey);
    } else {
      next.delete(templateKey);
    }
    openTemplateKeys = next;
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

  async function submitPuzzleUpdate(
    template: AdminPuzzleTemplate,
    event: SubmitEvent,
  ): Promise<void> {
    const form = event.currentTarget;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const sourceCode = sourceEditorViews.get(template.template_key)?.state.doc.toString() ?? "";
    if (!sourceCode.trim()) {
      localError = "Puzzle source code is required.";
      return;
    }

    localError = "";
    await updatePuzzleTemplate({
      ...template,
      source_code: sourceCode,
    });
  }

  async function confirmDeletePuzzle(template: AdminPuzzleTemplate): Promise<void> {
    const confirmed = window.confirm(
      `Delete puzzle template ${template.template_key}? This removes its source file.`,
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
        <p class="admin-muted">Manage accounts, ELO values, active matches, and puzzle sources.</p>
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
                  class="admin-input"
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
                class="btn admin-delete-btn"
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
          <span>{filteredPuzzleTemplates.length} of {adminPuzzleTemplates.length}</span>
        </div>

        <section class="admin-puzzle-toolbar">
          <div class="admin-puzzle-create">
            <label class="admin-filter-field">
              <span>New Template Key</span>
              <input
                class="admin-input"
                type="text"
                placeholder="example-template-v1"
                bind:value={newTemplateKey}
                disabled={busy}
              />
            </label>
            <label class="admin-filter-field">
              <span>Theme</span>
              <select class="admin-input" bind:value={newTemplateTheme} disabled={busy}>
                <option value="Cryptography">Cryptography</option>
                <option value="Algorithms">Algorithms</option>
                <option value="Numeric">Numeric</option>
              </select>
            </label>
            <label class="admin-filter-field">
              <span>Difficulty</span>
              <select class="admin-input" bind:value={newTemplateDifficulty} disabled={busy}>
                <option value="easy">easy</option>
                <option value="medium">medium</option>
                <option value="hard">hard</option>
                <option value="expert">expert</option>
              </select>
            </label>
            <button
              type="button"
              class="btn admin-save-btn"
              on:click={() => void submitCreatePuzzleTemplate()}
              disabled={busy}
            >
              Add Template
            </button>
          </div>

          <label class="admin-filter-field">
            <span>Search</span>
            <input
              class="admin-input"
              type="search"
              placeholder="key, prompt, hint, path"
              bind:value={puzzleFilterQuery}
              disabled={busy}
            />
          </label>

          <label class="admin-filter-field">
            <span>Theme</span>
            <select class="admin-input" bind:value={puzzleFilterTheme} disabled={busy}>
              <option value="all">All themes</option>
              {#each availableTemplateThemes as themeOption}
                <option value={themeOption}>{themeOption}</option>
              {/each}
            </select>
          </label>

          <label class="admin-filter-field">
            <span>Difficulty</span>
            <select class="admin-input" bind:value={puzzleFilterDifficulty} disabled={busy}>
              <option value="all">All difficulties</option>
              <option value="easy">easy</option>
              <option value="medium">medium</option>
              <option value="hard">hard</option>
              <option value="expert">expert</option>
            </select>
          </label>

          <div class="admin-filter-actions">
            <button type="button" class="btn" on:click={resetPuzzleFilters} disabled={busy}>
              Clear Filters
            </button>
            <button
              type="button"
              class="btn"
              on:click={expandFilteredTemplates}
              disabled={busy || filteredPuzzleTemplates.length === 0}
            >
              Expand Filtered
            </button>
            <button type="button" class="btn" on:click={collapseAllTemplates} disabled={busy}>
              Collapse All
            </button>
          </div>
        </section>

        {#if filteredPuzzleTemplates.length === 0}
          <p class="admin-muted">No puzzle templates match the current filters.</p>
        {:else}
          <div class="admin-puzzle-list">
            {#each filteredPuzzleTemplates as template (template.template_key)}
              <details
                class="admin-puzzle-item"
                open={openTemplateKeys.has(template.template_key)}
                on:toggle={(event) => syncTemplateOpenState(template.template_key, event)}
              >
                <summary class="admin-puzzle-summary">
                  <div class="admin-puzzle-summary-copy">
                    <strong>{template.template_key}</strong>
                    <p class="admin-muted">{template.theme} · {template.difficulty.toUpperCase()}</p>
                  </div>
                  <span class="admin-puzzle-summary-tag">
                    {#if openTemplateKeys.has(template.template_key)}Open{:else}Collapsed{/if}
                  </span>
                </summary>

                <form
                  class="admin-puzzle-form"
                  on:submit|preventDefault={(event) => void submitPuzzleUpdate(template, event)}
                >
                  <div class="admin-puzzle-meta-grid">
                    <p>
                      <span>Theme</span>
                      <strong>{template.theme}</strong>
                    </p>
                    <p>
                      <span>Difficulty</span>
                      <strong>{template.difficulty.toUpperCase()}</strong>
                    </p>
                    <p class="admin-puzzle-path">
                      <span>File</span>
                      <code>{template.source_path}</code>
                    </p>
                  </div>

                  <div class="admin-source-field">
                    <span>Puzzle Source (Python)</span>
                    <div
                      class="admin-source-editor"
                      use:sourceEditorHost={{
                        templateKey: template.template_key,
                        sourceCode: template.source_code,
                      }}
                    ></div>
                  </div>

                  <div class="admin-puzzle-actions">
                    <button type="submit" class="btn admin-save-btn" disabled={busy}>
                      Save Source
                    </button>
                    <button
                      type="button"
                      class="btn admin-delete-btn"
                      disabled={busy}
                      on:click={() => void confirmDeletePuzzle(template)}
                    >
                      Delete Template
                    </button>
                  </div>
                </form>
              </details>
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
