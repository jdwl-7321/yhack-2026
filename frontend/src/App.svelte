<script lang="ts">
  import { onMount, tick } from 'svelte'

  type UiTheme = 'light' | 'dark' | 'system'
  type Mode = 'zen' | 'casual' | 'ranked'
  type Difficulty = 'easy' | 'medium' | 'hard' | 'expert'

  type Standing = {
    placement: number
    user_id: string
    name: string
    elo: number
    solved: boolean
    hidden_passed: number
    hint_level: number
    forfeited: boolean
    rating_delta: number
  }

  type MatchPayload = {
    match_id: string
    mode: Mode
    theme: string
    difficulty: Difficulty
    time_limit_seconds: number
    prompt: string
    scaffold: string
    sample_tests: Array<{ input: string; output: string }>
    standings: Standing[]
  }

  type SubmitPayload = {
    verdict: 'accepted' | 'sample_failed' | 'wrong_answer' | 'error'
    sample_passed: number
    sample_total: number
    hidden_passed: number
    hidden_total: number
    runtime_ms: number
    message: string
    standings: Standing[]
  }

  const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
  const FALLBACK_THEME = 'String manipulation (unix-like text processing)'
  const INDENT = '    '
  const PYTHON_TOKEN_PATTERN =
    /(#.*$)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|\b(\d+(?:\.\d+)?)\b|\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b/gm

  const modeOptions: Mode[] = ['zen', 'casual', 'ranked']
  const difficultyOptions: Difficulty[] = ['easy', 'medium', 'hard', 'expert']
  const themeOptions: UiTheme[] = ['light', 'dark', 'system']

  let displayName = 'Player'
  let isGuest = false
  let elo = 1000
  let mode: Mode = 'zen'
  let difficulty: Difficulty = 'easy'
  let selectedTheme = FALLBACK_THEME
  let timeLimitSeconds = 900
  let seed = Math.floor(Math.random() * 1_000_000)

  let themePref: UiTheme = 'system'
  let systemMatcher: MediaQueryList | null = null
  let mediaListener: (() => void) | null = null

  let themes = [FALLBACK_THEME]
  let userId = ''
  let match: MatchPayload | null = null
  let standings: Standing[] = []
  let code = ''
  let hintOne = ''
  let hintTwo = ''
  let submitResult: SubmitPayload | null = null
  let highlightedCode = ' '
  let lineCount = 1
  let lineNumbers: HTMLDivElement | null = null
  let highlightLayer: HTMLPreElement | null = null

  let busy = false
  let error = ''
  let notice = ''

  function escapeHtml(value: string): string {
    return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  }

  function highlightPython(source: string): string {
    let html = ''
    let lastIndex = 0

    for (const match of source.matchAll(PYTHON_TOKEN_PATTERN)) {
      const index = match.index ?? 0
      const token = match[0]
      html += escapeHtml(source.slice(lastIndex, index))

      const className = match[1]
        ? 'editor-token-comment'
        : match[2]
          ? 'editor-token-string'
          : match[3]
            ? 'editor-token-number'
            : 'editor-token-keyword'

      html += `<span class="${className}">${escapeHtml(token)}</span>`
      lastIndex = index + token.length
    }

    html += escapeHtml(source.slice(lastIndex))
    return html || ' '
  }

  function syncEditorScroll(event: Event): void {
    const target = event.currentTarget as HTMLTextAreaElement
    if (highlightLayer) {
      highlightLayer.scrollTop = target.scrollTop
      highlightLayer.scrollLeft = target.scrollLeft
    }
    if (lineNumbers) {
      lineNumbers.scrollTop = target.scrollTop
    }
  }

  function handleEditorKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') {
      return
    }
    event.preventDefault()

    const target = event.currentTarget as HTMLTextAreaElement
    const { selectionStart, selectionEnd } = target

    if (selectionStart === selectionEnd) {
      code = `${code.slice(0, selectionStart)}${INDENT}${code.slice(selectionEnd)}`
      const cursor = selectionStart + INDENT.length
      void tick().then(() => {
        target.selectionStart = cursor
        target.selectionEnd = cursor
      })
      return
    }

    const selection = code.slice(selectionStart, selectionEnd)
    const indented = `${INDENT}${selection.replace(/\n/g, `\n${INDENT}`)}`
    code = `${code.slice(0, selectionStart)}${indented}${code.slice(selectionEnd)}`
    void tick().then(() => {
      target.selectionStart = selectionStart
      target.selectionEnd = selectionStart + indented.length
    })
  }

  function resolveTheme(pref: UiTheme): 'light' | 'dark' {
    if (pref === 'light' || pref === 'dark') {
      return pref
    }
    return systemMatcher?.matches ? 'dark' : 'light'
  }

  function applyTheme(pref: UiTheme): void {
    document.documentElement.dataset.theme = resolveTheme(pref)
  }

  function setTheme(pref: UiTheme): void {
    themePref = pref
    localStorage.setItem('yhack.theme', pref)
    applyTheme(pref)
  }

  function toErrorMessage(value: unknown): string {
    if (value instanceof Error) {
      return value.message
    }
    return 'Unexpected error'
  }

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    })
    const data = (await response.json().catch(() => ({}))) as { error?: string }
    if (!response.ok) {
      throw new Error(data.error ?? `Request failed (${response.status})`)
    }
    return data as T
  }

  async function loadThemes(): Promise<void> {
    const payload = await api<{ themes: string[] }>('/api/themes')
    if (payload.themes.length > 0) {
      themes = payload.themes
      if (!themes.includes(selectedTheme)) {
        selectedTheme = themes[0]
      }
    }
  }

  async function startMatch(): Promise<void> {
    busy = true
    error = ''
    notice = ''
    submitResult = null
    hintOne = ''
    hintTwo = ''
    try {
      const user = await api<{ id: string }>('/api/users', {
        method: 'POST',
        body: JSON.stringify({ name: displayName, guest: isGuest, elo }),
      })
      userId = user.id

      const party = await api<{ code: string }>('/api/parties', {
        method: 'POST',
        body: JSON.stringify({
          leader_id: user.id,
          mode,
          theme: selectedTheme,
          difficulty,
          time_limit_seconds: mode === 'ranked' ? 3600 : timeLimitSeconds,
          seed,
        }),
      })

      const payload = await api<MatchPayload>(`/api/parties/${party.code}/start`, {
        method: 'POST',
        body: JSON.stringify({ seed }),
      })

      match = payload
      standings = payload.standings
      code = payload.scaffold
      if (payload.mode !== mode) {
        notice = `Mode switched to ${payload.mode.toUpperCase()} due to ranked eligibility.`
      }
    } catch (err) {
      error = toErrorMessage(err)
      match = null
      standings = []
    } finally {
      busy = false
    }
  }

  async function submit(): Promise<void> {
    if (!match || !userId) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<SubmitPayload>(`/api/matches/${match.match_id}/submit`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, code }),
      })
      submitResult = payload
      standings = payload.standings
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function requestHint(level: 1 | 2): Promise<void> {
    if (!match || !userId) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<{ hint: string }>(`/api/matches/${match.match_id}/hint`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, level }),
      })
      if (level === 1) {
        hintOne = payload.hint
      } else {
        hintTwo = payload.hint
      }
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function forfeit(): Promise<void> {
    if (!match || !userId) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<{ standings: Standing[] }>(
        `/api/matches/${match.match_id}/forfeit`,
        {
          method: 'POST',
          body: JSON.stringify({ user_id: userId }),
        },
      )
      standings = payload.standings
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function finishMatch(): Promise<void> {
    if (!match) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<{ standings: Standing[] }>(`/api/matches/${match.match_id}/finish`, {
        method: 'POST',
      })
      standings = payload.standings
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  $: if (mode === 'ranked') {
    timeLimitSeconds = 3600
  }

  $: lineCount = Math.max(1, code.split('\n').length)
  $: highlightedCode = highlightPython(code)

  onMount(() => {
    const saved = localStorage.getItem('yhack.theme')
    if (saved === 'light' || saved === 'dark' || saved === 'system') {
      themePref = saved
    }

    systemMatcher = window.matchMedia('(prefers-color-scheme: dark)')
    applyTheme(themePref)

    mediaListener = () => {
      if (themePref === 'system') {
        applyTheme(themePref)
      }
    }
    systemMatcher.addEventListener('change', mediaListener)

    void loadThemes().catch((err) => {
      error = toErrorMessage(err)
    })

    return () => {
      if (systemMatcher && mediaListener) {
        systemMatcher.removeEventListener('change', mediaListener)
      }
    }
  })
</script>

<div class="shell">
  <header class="masthead">
    <p class="eyebrow">YHACK-2026 / INITIAL PROTOTYPE</p>
    <h1>Infer the rule. Ship the solver.</h1>
    <p class="subtext">
      Fast end-to-end loop with puzzle generation, hidden judging, hints, party modes, and ranked
      fallback logic.
    </p>
  </header>

  <main class="layout">
    <section class="panel controls">
      <h2>Session Control</h2>

      <label>
        <span>Display name</span>
        <input bind:value={displayName} maxlength="24" />
      </label>

      <label class="inline">
        <input type="checkbox" bind:checked={isGuest} />
        <span>Guest account</span>
      </label>

      <label>
        <span>Player ELO</span>
        <input type="number" bind:value={elo} min="100" max="3000" />
      </label>

      <label>
        <span>Mode</span>
        <select bind:value={mode}>
          {#each modeOptions as option}
            <option value={option}>{option.toUpperCase()}</option>
          {/each}
        </select>
      </label>

      <label>
        <span>Puzzle theme</span>
        <select bind:value={selectedTheme} disabled={mode === 'ranked'}>
          {#each themes as theme}
            <option value={theme}>{theme}</option>
          {/each}
        </select>
      </label>

      <label>
        <span>Difficulty</span>
        <select bind:value={difficulty} disabled={mode === 'ranked'}>
          {#each difficultyOptions as option}
            <option value={option}>{option.toUpperCase()}</option>
          {/each}
        </select>
      </label>

      <label>
        <span>Time limit (seconds)</span>
        <input type="number" bind:value={timeLimitSeconds} min="60" max="7200" disabled={mode === 'ranked'} />
      </label>

      <label>
        <span>Seed</span>
        <input type="number" bind:value={seed} />
      </label>

      <div class="theme-switcher">
        <span>UI Theme</span>
        <div class="switch-row">
          {#each themeOptions as option}
            <button
              type="button"
              class:active={themePref === option}
              on:click={() => setTheme(option)}
            >
              {option}
            </button>
          {/each}
        </div>
      </div>

      <button class="primary" on:click={startMatch} disabled={busy}>Start Match</button>

      {#if notice}
        <p class="notice">{notice}</p>
      {/if}
      {#if error}
        <p class="error">{error}</p>
      {/if}
    </section>

    <section class="panel arena">
      {#if !match}
        <p class="empty">Start a match to load prompt, samples, and editor scaffold.</p>
      {:else}
        <header class="arena-head">
          <h2>{match.theme}</h2>
          <p class="mono">
            {match.mode.toUpperCase()} · {match.difficulty.toUpperCase()} · {match.time_limit_seconds}s
          </p>
        </header>

        <p class="prompt">{match.prompt}</p>

        <div class="sample-grid">
          {#each match.sample_tests as sample, index}
            <article class="sample-card">
              <h3>Sample {index + 1}</h3>
              <p><strong>Input</strong></p>
              <pre>{sample.input}</pre>
              <p><strong>Output</strong></p>
              <pre>{sample.output}</pre>
            </article>
          {/each}
        </div>

        <label class="editor-label">
          <span>Python submission</span>
          <div class="editor-shell">
            <div class="editor-lines" bind:this={lineNumbers} aria-hidden="true">
              {#each Array(lineCount) as _, index (index)}
                <span>{index + 1}</span>
              {/each}
            </div>
            <div class="editor-stack">
              <pre class="editor-highlight" bind:this={highlightLayer} aria-hidden="true">{@html highlightedCode}</pre>
              <textarea
                class="editor-input"
                bind:value={code}
                spellcheck="false"
                autocomplete="off"
                wrap="off"
                on:keydown={handleEditorKeydown}
                on:scroll={syncEditorScroll}
              ></textarea>
            </div>
          </div>
        </label>

        <div class="action-row">
          <button class="primary" on:click={submit} disabled={busy}>Submit</button>
          <button class="ghost" on:click={() => requestHint(1)} disabled={busy}>Hint 1</button>
          <button class="ghost" on:click={() => requestHint(2)} disabled={busy}>Hint 2</button>
          <button class="ghost" on:click={forfeit} disabled={busy}>Forfeit</button>
          <button class="ghost" on:click={finishMatch} disabled={busy}>Finish</button>
        </div>

        {#if submitResult}
          <p class="chip" class:ok={submitResult.verdict === 'accepted'} class:bad={submitResult.verdict !== 'accepted'}>
            {submitResult.verdict.toUpperCase()} · SAMPLE {submitResult.sample_passed}/{submitResult.sample_total} · HIDDEN {submitResult.hidden_passed}/{submitResult.hidden_total} · {submitResult.runtime_ms}ms
          </p>
          {#if submitResult.message}
            <p class="mono subtle">{submitResult.message}</p>
          {/if}
        {/if}

        {#if hintOne}
          <p class="hint"><strong>Hint 1:</strong> {hintOne}</p>
        {/if}
        {#if hintTwo}
          <p class="hint"><strong>Hint 2:</strong> {hintTwo}</p>
        {/if}

        <section class="standings">
          <h3>Standings</h3>
          <ul>
            {#each standings as row}
              <li>
                <span class="mono">#{row.placement}</span>
                <span>{row.name}</span>
                <span class="mono">hidden {row.hidden_passed}</span>
                <span class="mono">hint {row.hint_level}</span>
                <span class="mono">ELO {row.elo}</span>
                <span class="mono delta">{row.rating_delta >= 0 ? '+' : ''}{row.rating_delta}</span>
                <span class="state" class:ok={row.solved} class:bad={!row.solved}>
                  {row.forfeited ? 'FORFEIT' : row.solved ? 'SOLVED' : 'OPEN'}
                </span>
              </li>
            {/each}
          </ul>
        </section>
      {/if}
    </section>
  </main>
</div>
