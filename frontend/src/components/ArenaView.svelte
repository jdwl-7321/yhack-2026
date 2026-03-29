<script lang="ts">
  import type {
    ConsoleEntry,
    JudgePayload,
    KeybindMode,
    MatchPayload,
    SessionUser,
    Standing,
  } from "../app-types";

  export let sessionUser: SessionUser | null = null;
  export let match: MatchPayload | null = null;
  export let busy = false;
  export let timerText = "00:00";
  export let keybindMode: KeybindMode = "normal";
  export let editorFontSize = 14;
  export let lineNumbers = "1";
  export let editorScrollLeft = 0;
  export let highlightedCode = "";
  export let code = "";
  export let hints: string[] = [];
  export let submitResult: JudgePayload | null = null;
  export let testResult: JudgePayload | null = null;
  export let standings: Standing[] = [];
  export let notice = "";
  export let error = "";
  export let consoleEntries: ConsoleEntry[] = [];

  export let lineNumbersEl: HTMLPreElement | null = null;
  export let highlightEl: HTMLPreElement | null = null;
  export let consoleEl: HTMLDivElement | null = null;
  export let vimEditorHostEl: HTMLDivElement | null = null;

  export let launchConfiguredMatch: () => void | Promise<void> = () => {};
  export let showHome: () => void = () => {};
  export let raceModeIcon: (value: MatchPayload["mode"]) => string = () => "fa-mountain";
  export let promoteFailedTest: () => void | Promise<void> = () => {};
  export let requestHint: () => void | Promise<void> = () => {};
  export let forfeit: () => void | Promise<void> = () => {};
  export let testSamples: () => void | Promise<void> = () => {};
  export let submit: () => void | Promise<void> = () => {};
  export let handleEditorInput: (event: Event) => void = () => {};
  export let handleEditorKeydown: (event: KeyboardEvent) => void = () => {};
  export let syncEditorScroll: (event: Event) => void = () => {};
  export let formatRatingDelta: (value: number) => string = (value) => String(value);
</script>

<main id="race-view">
  {#if !sessionUser}
    <section class="race-empty">
      <p>Sign in to start a match.</p>
      <button type="button" class="btn primary" on:click={showHome}>Back Home</button>
    </section>
  {:else if !match}
    <section class="race-empty">
      <p>
        Start a match from Home to load samples and the editor scaffold.
      </p>
      <button type="button" class="btn" on:click={showHome}>Back Home</button>
      <button
        type="button"
        class="btn primary"
        on:click={launchConfiguredMatch}
        disabled={busy}
      >
        Start Match
      </button>
    </section>
  {:else}
    <div class="test-config">
      <div class="group">
        <span id="header-mode"
          ><i class={`fas ${raceModeIcon(match.mode)}`} aria-hidden="true"
          ></i>
          {match.mode}</span
        >
      </div>
      <div class="divider"></div>
      <div class="group">
        <span
          ><i class="fas fa-brain" aria-hidden="true"></i>
          {match.theme}</span
        >
      </div>
      <div class="divider"></div>
      <div class="group">
        <span
          ><i class="fas fa-layer-group" aria-hidden="true"></i>
          {match.difficulty}</span
        >
      </div>
      <div class="divider"></div>
      <div class="group">
        <span class="active-text"
          ><i class="fas fa-clock" aria-hidden="true"></i> {timerText}</span
        >
      </div>
    </div>

    <div class="game-layout">
      <section class="prompt-panel">
        <article class="prompt-card">
          {#if match.sample_tests.length > 0}
            <section class="samples-panel">
              <p class="samples-title">Samples</p>
              <div class="samples-scroll">
                <div class="samples-grid">
                  <span class="sample-head index-head">#</span>
                  <span class="sample-head">Input</span>
                  <span class="sample-head">Output</span>
                  {#each match.sample_tests as sample, index}
                    <span class="sample-index">{index + 1}</span>
                    <pre class="sample-cell">{sample.input}</pre>
                    <pre class="sample-cell">{sample.output}</pre>
                  {/each}
                </div>
              </div>
            </section>
          {:else}
            <p class="standings-empty">No sample tests available.</p>
          {/if}

          {#if hints.length > 0}
            <div class="hint-stack">
              {#each hints as hintText, index}
                <p class="hint-item">Hint {index + 1}: {hintText}</p>
              {/each}
            </div>
          {/if}

          {#if submitResult?.first_failed_hidden_test}
            <div class="failed-case">
              <h3>First failed hidden test</h3>
              <p>Input</p>
              <pre>{submitResult.first_failed_hidden_test.input_str}</pre>
              <p>Expected output</p>
              <pre>{submitResult.first_failed_hidden_test
                  .expected_output}</pre>
              <p>Your output</p>
              <pre>{submitResult.first_failed_hidden_test
                  .actual_output}</pre>
              <button
                type="button"
                class="btn"
                on:click={promoteFailedTest}
                disabled={busy}
              >
                Use as sample test
              </button>
            </div>
          {/if}
        </article>
      </section>

      <section class="editor-panel">
          <div
            class="editor-container"
            style={`--editor-font-size: ${editorFontSize}px;`}
          >
            <div class="editor-stack">
              {#if keybindMode === "vim"}
                <div class="vim-editor-host" bind:this={vimEditorHostEl}></div>
              {:else}
                <pre
                  class="line-numbers"
                  aria-hidden="true"
                  bind:this={lineNumbersEl}
                  style:transform={`translateX(${-editorScrollLeft}px)`}
                  ><code>{lineNumbers}</code></pre
                >
                <pre class="code-highlight" aria-hidden="true" bind:this={highlightEl}
                  ><code class="hljs language-python">{@html highlightedCode || " "}</code></pre
                >
                <textarea
                  id="code-editor"
                  bind:value={code}
                  spellcheck="false"
                  autocomplete="off"
                  wrap="off"
                  on:input={handleEditorInput}
                  on:keydown={handleEditorKeydown}
                  on:scroll={syncEditorScroll}
                ></textarea>
              {/if}
            </div>

          <div class="editor-actions">
            {#if keybindMode === "custom"}
              <span class="editor-mode-badge">
                custom shortcuts
              </span>
            {/if}
            <button
              type="button"
              class="btn"
              on:click={requestHint}
              disabled={busy || hints.length >= 3}
            >
              <i class="fas fa-lightbulb" aria-hidden="true"></i> Hint
            </button>

            <div class="action-group">
              <button
                type="button"
                class="btn"
                on:click={forfeit}
                disabled={busy}
              >
                <i class="fas fa-flag" aria-hidden="true"></i> Forfeit
              </button>
              <button
                type="button"
                class="btn"
                on:click={testSamples}
                disabled={busy}
              >
                <i class="fas fa-vial" aria-hidden="true"></i> Run Samples
              </button>
              <button
                type="button"
                class="btn primary"
                on:click={submit}
                disabled={busy}
              >
                {#if busy}
                  <i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Running...
                {:else}
                  <i class="fas fa-play" aria-hidden="true"></i> Submit
                {/if}
              </button>
            </div>
          </div>
        </div>

        <div class="console" id="console" bind:this={consoleEl}>
          {#each consoleEntries as entry (entry.id)}
            <div class={`console-line ${entry.type}`}>{entry.text}</div>
          {/each}
        </div>

        {#if testResult}
          <p
            class="result-pill"
            class:success={testResult.verdict === "accepted"}
            class:error={testResult.verdict !== "accepted"}
          >
            TEST: {testResult.verdict} | sample {testResult.sample_passed}/{testResult.sample_total}
            | {testResult.runtime_ms}ms
          </p>
        {/if}

        {#if submitResult}
          <p
            class="result-pill"
            class:success={submitResult.verdict === "accepted"}
            class:error={submitResult.verdict !== "accepted"}
          >
            SUBMIT: {submitResult.verdict} | sample {submitResult.sample_passed}/{submitResult.sample_total}
            | hidden {submitResult.hidden_passed}/{submitResult.hidden_total}
            | {submitResult.runtime_ms}ms
          </p>
        {/if}
      </section>
    </div>

    <section class="standings-card">
      <div class="standings-head">
        <h3>Standings</h3>
        <button type="button" class="btn" on:click={showHome}>Back Home</button>
      </div>

      {#if standings.length === 0}
        <p class="standings-empty">No standings yet.</p>
      {:else}
        <div class="standings-list">
          {#each standings as row}
            <article class="standing-row">
              <span class="mono">#{row.placement}</span>
              <span class="name">{row.name}</span>
              <span class="mono">hidden {row.hidden_passed}</span>
              <span class="mono">hint {row.hint_level}</span>
              <span class="mono">ELO {row.elo}</span>
              <span class="mono delta"
                >{formatRatingDelta(row.rating_delta)}</span
              >
              <span
                class="state"
                class:ok={row.solved}
                class:bad={!row.solved}
              >
                {row.forfeited ? "FORFEIT" : row.solved ? "SOLVED" : "OPEN"}
              </span>
            </article>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error}
    <p class="flash error">{error}</p>
  {/if}
</main>
