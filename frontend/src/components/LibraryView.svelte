<script lang="ts">
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import type {
    CollectionRunMode,
    SessionUser,
    UserCollectionPayload,
    UserPuzzlePayload,
  } from "../app-types";

  hljs.registerLanguage("python", python);

  export let sessionUser: SessionUser | null = null;
  export let busy = false;
  export let notice = "";
  export let error = "";

  export let puzzles: UserPuzzlePayload[] = [];
  export let collections: UserCollectionPayload[] = [];
  export let currentPuzzle: UserPuzzlePayload | null = null;
  export let currentCollection: UserCollectionPayload | null = null;
  export let activeKind: "puzzle" | "collection" | null = null;
  export let shareRoute = false;
  export let keybindMode: "normal" | "vim" | "custom" = "normal";

  export let newPuzzleTitle = "";
  export let newCollectionTitle = "";
  export let puzzleDraftTitle = "";
  export let puzzleDraftSource = "";
  export let collectionDraftTitle = "";
  export let collectionDraftPuzzleIds: string[] = [];
  export let previewCollectionRunMode: CollectionRunMode = "fixed";

  export let showHome: () => void = () => {};
  export let openPuzzle: (slug: string) => void | Promise<void> = () => {};
  export let openCollection: (slug: string) => void | Promise<void> = () => {};
  export let createPuzzle: () => void | Promise<void> = () => {};
  export let createCollection: () => void | Promise<void> = () => {};
  export let savePuzzle: () => void | Promise<void> = () => {};
  export let saveCollection: () => void | Promise<void> = () => {};
  export let copyShareLink: (sharePath: string) => void | Promise<void> = () => {};
  export let usePreviewInSetup: () => void | Promise<void> = () => {};
  export let addCollectionPuzzle: (puzzleId: string) => void = () => {};
  export let removeCollectionPuzzle: (puzzleId: string) => void = () => {};
  export let moveCollectionPuzzle: (puzzleId: string, direction: -1 | 1) => void = () => {};
  export let libraryVimEditorHostEl: HTMLDivElement | null = null;

  let puzzleWorkspaceTab: "main" | "editor" = "main";
  let librarySourceLineNumbersEl: HTMLPreElement | null = null;
  let librarySourceHighlightEl: HTMLPreElement | null = null;
  let librarySourceScrollLeft = 0;

  $: editingPuzzle = activeKind === "puzzle" ? currentPuzzle : null;
  $: editingCollection = activeKind === "collection" ? currentCollection : null;
  $: canShowPuzzleWorkspaceTabs = !!sessionUser && !shareRoute;
  $: if (canShowPuzzleWorkspaceTabs && puzzleWorkspaceTab === "editor" && !editingPuzzle) {
    puzzleWorkspaceTab = "main";
  }
  $: availableCollectionAdditions = puzzles.filter(
    (puzzle) => !collectionDraftPuzzleIds.includes(puzzle.id ?? ""),
  );
  $: librarySourceLineNumbers = Array.from(
    { length: Math.max(1, puzzleDraftSource.split("\n").length) },
    (_, index) => `${index + 1}`,
  ).join("\n");
  $: librarySourceHighlighted = puzzleDraftSource
    ? hljs.highlight(puzzleDraftSource, {
        language: "python",
        ignoreIllegals: true,
      }).value
    : "";

  function syncLibrarySourceScroll(event: Event): void {
    if (!librarySourceHighlightEl) {
      return;
    }
    const target = event.currentTarget as HTMLTextAreaElement;
    librarySourceScrollLeft = target.scrollLeft;
    librarySourceHighlightEl.scrollTop = target.scrollTop;
    librarySourceHighlightEl.scrollLeft = target.scrollLeft;
    if (librarySourceLineNumbersEl) {
      librarySourceLineNumbersEl.scrollTop = target.scrollTop;
    }
  }

  function handleLibrarySourceInput(event: Event): void {
    puzzleDraftSource = (event.currentTarget as HTMLTextAreaElement).value;
  }

  function openPuzzleEditor(slug: string): void {
    puzzleWorkspaceTab = "editor";
    void openPuzzle(slug);
  }
</script>

<main id="library-view">
  {#if !sessionUser && !shareRoute}
    <section class="race-empty">
      <p>Sign in to manage your puzzle library.</p>
      <button type="button" class="btn primary" on:click={showHome}>Back Home</button>
    </section>
  {:else}
    <section class="library-shell">
      <aside class="library-sidebar">
        <div class="library-sidebar-head">
          <div>
            <p class="eyebrow">Custom Content</p>
            <h2>{shareRoute ? "Share Preview" : "Your Library"}</h2>
          </div>
        </div>

        {#if sessionUser && !shareRoute}
          <div class="library-create-card library-widget">
            <label>
              <span>New puzzle</span>
              <input bind:value={newPuzzleTitle} placeholder="Offset warmup" maxlength="80" />
            </label>
            <button
              type="button"
              class="btn primary wide"
              on:click={createPuzzle}
              disabled={busy || newPuzzleTitle.trim().length < 3}
            >
              Create puzzle
            </button>
          </div>

          <div class="library-create-card library-widget">
            <label>
              <span>New collection</span>
              <input bind:value={newCollectionTitle} placeholder="Round one set" maxlength="80" />
            </label>
            <button
              type="button"
              class="btn primary wide"
              on:click={createCollection}
              disabled={busy || newCollectionTitle.trim().length < 3 || puzzles.length === 0}
            >
              Create collection
            </button>
          </div>
        {/if}

        {#if collections.length > 0}
          <section class="library-list-card library-widget">
            <p class="eyebrow">Collections</p>
            <div class="library-list">
              {#each collections as collection}
                <button
                  type="button"
                  class="library-list-item"
                  class:active={editingCollection?.slug === collection.slug}
                  on:click={() => void openCollection(collection.slug)}
                >
                  <strong>{collection.title}</strong>
                  <span>{collection.puzzle_count} puzzle{collection.puzzle_count === 1 ? "" : "s"}</span>
                </button>
              {/each}
            </div>
          </section>
        {/if}
      </aside>

      <section class="library-detail">
        {#if editingCollection}
          <article class="library-editor-card">
            <div class="library-editor-head">
              <div>
                <p class="eyebrow">{editingCollection.can_edit ? "Collection Editor" : "Collection Preview"}</p>
                <h2>{editingCollection.title}</h2>
                <p class="library-meta">
                  by {editingCollection.owner.name} · <span class="mono">/collections/{editingCollection.slug}</span>
                </p>
              </div>
              <div class="library-action-row library-widget compact">
                <label class="compact-select">
                  <span>Run mode</span>
                  <select bind:value={previewCollectionRunMode}>
                    <option value="fixed">Fixed</option>
                    <option value="random">Random</option>
                  </select>
                </label>
                <button
                  type="button"
                  class="btn"
                  on:click={() => void copyShareLink(editingCollection.share_path)}
                >
                  Copy share link
                </button>
                <button type="button" class="btn" on:click={usePreviewInSetup}>
                  Use in setup
                </button>
              </div>
            </div>

            {#if editingCollection.can_edit}
              <label>
                <span>Title</span>
                <input bind:value={collectionDraftTitle} maxlength="80" />
              </label>

              <div class="collection-membership-grid">
                <section class="collection-membership-card library-widget">
                  <p class="eyebrow">In collection</p>
                  {#if collectionDraftPuzzleIds.length === 0}
                    <p class="library-preview-note">Add at least one puzzle to save this collection.</p>
                  {:else}
                    <div class="library-list">
                      {#each collectionDraftPuzzleIds as puzzleId, index}
                        {@const puzzle = puzzles.find((item) => item.id === puzzleId)}
                        {#if puzzle}
                          <div class="collection-item-row">
                            <div>
                              <strong>{puzzle.title}</strong>
                              <span>{puzzle.slug}</span>
                            </div>
                            <div class="collection-item-actions">
                              <button
                                type="button"
                                class="btn"
                                on:click={() => moveCollectionPuzzle(puzzleId, -1)}
                                disabled={index === 0}
                              >
                                Up
                              </button>
                              <button
                                type="button"
                                class="btn"
                                on:click={() => moveCollectionPuzzle(puzzleId, 1)}
                                disabled={index === collectionDraftPuzzleIds.length - 1}
                              >
                                Down
                              </button>
                              <button
                                type="button"
                                class="btn"
                                on:click={() => removeCollectionPuzzle(puzzleId)}
                              >
                                Remove
                              </button>
                            </div>
                          </div>
                        {/if}
                      {/each}
                    </div>
                  {/if}
                </section>

                <section class="collection-membership-card library-widget">
                  <p class="eyebrow">Available puzzles</p>
                  <div class="library-list">
                    {#each availableCollectionAdditions as puzzle}
                      <button
                        type="button"
                        class="library-list-item"
                        on:click={() => addCollectionPuzzle(puzzle.id ?? "")}
                      >
                        <strong>{puzzle.title}</strong>
                        <span>{puzzle.slug}</span>
                      </button>
                    {/each}
                  </div>
                </section>
              </div>

              <button
                type="button"
                class="btn primary"
                on:click={saveCollection}
                disabled={busy || collectionDraftTitle.trim().length < 3 || collectionDraftPuzzleIds.length === 0}
              >
                Save collection
              </button>
            {:else}
              <div class="library-preview-note">
                <p>This is a play-only collection preview. Only the creator can manage its members.</p>
              </div>
            {/if}
          </article>
        {:else}
          {#if canShowPuzzleWorkspaceTabs}
            <div class="library-tab-row library-widget compact">
              <button
                type="button"
                class="btn"
                class:primary={puzzleWorkspaceTab === "main"}
                on:click={() => (puzzleWorkspaceTab = "main")}
              >
                Puzzles
              </button>
              <button
                type="button"
                class="btn"
                class:primary={puzzleWorkspaceTab === "editor"}
                on:click={() => (puzzleWorkspaceTab = "editor")}
                disabled={!editingPuzzle}
              >
                Puzzle editor
              </button>
            </div>
          {/if}

          {#if shareRoute && editingPuzzle}
            <article class="library-editor-card">
              <div class="library-editor-head">
                <div>
                  <p class="eyebrow">Puzzle Preview</p>
                  <h2>{editingPuzzle.title}</h2>
                  <p class="library-meta">
                    by {editingPuzzle.owner.name} · <span class="mono">/puzzles/{editingPuzzle.slug}</span>
                  </p>
                </div>
                <div class="library-action-row">
                  <button
                    type="button"
                    class="btn"
                    on:click={() => void copyShareLink(editingPuzzle.share_path)}
                  >
                    Copy share link
                  </button>
                  <button type="button" class="btn" on:click={usePreviewInSetup}>
                    Use in setup
                  </button>
                </div>
              </div>

              <div class="library-preview-note">
                <p>This is a play-only preview. Only the creator can view or edit the source.</p>
              </div>
            </article>
          {:else if puzzleWorkspaceTab === "main"}
            <article class="library-editor-card">
              <div class="library-editor-head">
                <div>
                  <p class="eyebrow">Puzzles</p>
                  <h2>Your puzzle library</h2>
                </div>
              </div>

              {#if puzzles.length === 0}
                <p class="library-preview-note">Create a puzzle from the sidebar to start editing.</p>
              {:else}
                <div class="library-list">
                  {#each puzzles as puzzle}
                    <div
                      class="library-list-item library-puzzle-row"
                      class:active={editingPuzzle?.slug === puzzle.slug}
                      role="button"
                      tabindex="0"
                      on:click={() => openPuzzleEditor(puzzle.slug)}
                      on:keydown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openPuzzleEditor(puzzle.slug);
                        }
                      }}
                    >
                      <strong>{puzzle.title}</strong>
                      <button
                        type="button"
                        class="btn"
                        on:click|stopPropagation={() => void copyShareLink(puzzle.share_path)}
                      >
                        Copy link
                      </button>
                      <button
                        type="button"
                        class="btn"
                        on:click|stopPropagation={() => openPuzzleEditor(puzzle.slug)}
                      >
                        Open in editor
                      </button>
                    </div>
                  {/each}
                </div>
              {/if}
            </article>
          {:else if editingPuzzle}
            <article class="library-editor-card">
              <div class="library-editor-head">
                <div>
                  <p class="eyebrow">Puzzle Editor</p>
                  <h2>{editingPuzzle.title}</h2>
                  <p class="library-meta">
                    by {editingPuzzle.owner.name} · <span class="mono">/puzzles/{editingPuzzle.slug}</span>
                  </p>
                </div>
                <div class="library-action-row">
                  <button
                    type="button"
                    class="btn"
                    on:click={() => void copyShareLink(editingPuzzle.share_path)}
                  >
                    Copy share link
                  </button>
                  <button type="button" class="btn" on:click={usePreviewInSetup}>
                    Use in setup
                  </button>
                </div>
              </div>

              <label class="library-widget compact">
                <span>Title</span>
                <input bind:value={puzzleDraftTitle} maxlength="80" />
              </label>

              <label>
                <span>Source</span>
                <div class="editor-container library-source-shell">
                  <div class="editor-stack library-source-stack">
                    {#if keybindMode === "vim"}
                      <div class="vim-editor-host" bind:this={libraryVimEditorHostEl}></div>
                    {:else}
                      <pre
                        class="line-numbers"
                        aria-hidden="true"
                        bind:this={librarySourceLineNumbersEl}
                        style:transform={`translateX(${-librarySourceScrollLeft}px)`}
                        ><code>{librarySourceLineNumbers}</code></pre
                      >
                      <pre class="code-highlight" aria-hidden="true" bind:this={librarySourceHighlightEl}
                        ><code class="hljs language-python">{@html librarySourceHighlighted || " "}</code></pre
                      >
                      <textarea
                        class="library-code-editor"
                        value={puzzleDraftSource}
                        spellcheck="false"
                        on:input={handleLibrarySourceInput}
                        on:scroll={syncLibrarySourceScroll}
                      ></textarea>
                    {/if}
                  </div>
                </div>
              </label>

              <button
                type="button"
                class="btn primary"
                on:click={savePuzzle}
                disabled={busy || puzzleDraftTitle.trim().length < 3 || puzzleDraftSource.trim().length === 0}
              >
                Save puzzle
              </button>
            </article>
            {:else}
              <section class="race-empty">
                <p>Choose a puzzle in the Puzzles tab to open the editor.</p>
              </section>
            {/if}
        {/if}
      </section>
    </section>
  {/if}

  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error}
    <p class="flash error">{error}</p>
  {/if}
</main>
