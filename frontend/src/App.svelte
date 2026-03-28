<script lang="ts">
  import { onMount, tick } from 'svelte'

  type UiTheme = 'light' | 'dark' | 'system'
  type AuthMode = 'register' | 'login'
  type Mode = 'zen' | 'casual' | 'ranked'
  type Difficulty = 'easy' | 'medium' | 'hard' | 'expert'

  type SessionUser = {
    id: string
    name: string
    guest: boolean
    elo: number
  }

  type SessionPayload = {
    authenticated: boolean
    user?: SessionUser
  }

  type AuthResponse = {
    user: SessionUser
  }

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

  type FailedHiddenTest = {
    input_str: string
    expected_output: string
    actual_output: string
  }

  type JudgePayload = {
    verdict: 'accepted' | 'sample_failed' | 'wrong_answer' | 'error'
    sample_passed: number
    sample_total: number
    hidden_passed: number
    hidden_total: number
    runtime_ms: number
    message: string
    stdout: string
    first_failed_hidden_test: FailedHiddenTest | null
    sample_tests: Array<{ input: string; output: string }>
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

  let authMode: AuthMode = 'register'
  let authName = ''
  let authPassword = ''

  let sessionUser: SessionUser | null = null
  let inArena = false

  let mode: Mode = 'zen'
  let difficulty: Difficulty = 'easy'
  let selectedTheme = FALLBACK_THEME
  let timeLimitSeconds = 900
  let seed = Math.floor(Math.random() * 1_000_000)

  let themePref: UiTheme = 'system'
  let systemMatcher: MediaQueryList | null = null
  let mediaListener: (() => void) | null = null

  let themes = [FALLBACK_THEME]
  let match: MatchPayload | null = null
  let standings: Standing[] = []
  let code = ''
  let hintOne = ''
  let hintTwo = ''
  let testResult: JudgePayload | null = null
  let submitResult: JudgePayload | null = null
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
      credentials: 'include',
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

  function syncSessionElo(currentStandings: Standing[]): void {
    if (!sessionUser) {
      return
    }

    const self = currentStandings.find((row) => row.user_id === sessionUser?.id)
    if (self) {
      sessionUser = { ...sessionUser, elo: self.elo }
    }
  }

  async function refreshSession(): Promise<void> {
    const payload = await api<SessionPayload>('/api/auth/session')
    if (!payload.authenticated || !payload.user) {
      sessionUser = null
      inArena = false
      return
    }
    sessionUser = payload.user
  }

  async function authenticate(nextMode: AuthMode): Promise<void> {
    busy = true
    error = ''
    notice = ''
    try {
      const payload = await api<AuthResponse>(`/api/auth/${nextMode}`, {
        method: 'POST',
        body: JSON.stringify({ name: authName, password: authPassword }),
      })
      sessionUser = payload.user
      authPassword = ''
      notice = nextMode === 'register' ? 'Account created. Session is active.' : 'Signed in.'
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function logout(): Promise<void> {
    busy = true
    error = ''
    notice = ''
    try {
      await api<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })
      sessionUser = null
      inArena = false
      match = null
      standings = []
      testResult = null
      submitResult = null
      hintOne = ''
      hintTwo = ''
      code = ''
      notice = 'Signed out.'
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function startMatch(): Promise<void> {
    if (!sessionUser) {
      error = 'Sign in to start a match.'
      inArena = false
      return
    }

    busy = true
    error = ''
    notice = ''
    testResult = null
    submitResult = null
    hintOne = ''
    hintTwo = ''
    try {
      const party = await api<{ code: string }>('/api/parties', {
        method: 'POST',
        body: JSON.stringify({
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
      syncSessionElo(payload.standings)
      code = payload.scaffold
      inArena = true
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
    if (!match || !sessionUser) {
      return
    }
    const currentMatchId = match.match_id
    busy = true
    error = ''
    notice = ''
    try {
      const payload = await api<JudgePayload>(`/api/matches/${currentMatchId}/submit`, {
        method: 'POST',
        body: JSON.stringify({ code }),
      })
      submitResult = payload
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests }
      }
      standings = payload.standings
      syncSessionElo(payload.standings)
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function testSamples(): Promise<void> {
    if (!match || !sessionUser) {
      return
    }
    const currentMatchId = match.match_id
    busy = true
    error = ''
    notice = ''
    try {
      const payload = await api<JudgePayload>(`/api/matches/${currentMatchId}/test`, {
        method: 'POST',
        body: JSON.stringify({ code }),
      })
      testResult = payload
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests }
      }
      standings = payload.standings
      syncSessionElo(payload.standings)
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function promoteFailedTest(): Promise<void> {
    if (!match || !sessionUser || !submitResult?.first_failed_hidden_test) {
      return
    }
    const currentMatchId = match.match_id
    const currentSubmit = submitResult

    busy = true
    error = ''
    notice = ''
    try {
      const payload = await api<{ sample_tests: Array<{ input: string; output: string }> }>(
        `/api/matches/${currentMatchId}/promote-failed-test`,
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
      )
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests }
      }
      submitResult = { ...currentSubmit, first_failed_hidden_test: null }
      notice = 'Promoted failed hidden test to visible samples.'
    } catch (err) {
      error = toErrorMessage(err)
    } finally {
      busy = false
    }
  }

  async function requestHint(level: 1 | 2): Promise<void> {
    if (!match || !sessionUser) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<{ hint: string }>(`/api/matches/${match.match_id}/hint`, {
        method: 'POST',
        body: JSON.stringify({ level }),
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
    if (!match || !sessionUser) {
      return
    }
    busy = true
    error = ''
    try {
      const payload = await api<{ standings: Standing[] }>(
        `/api/matches/${match.match_id}/forfeit`,
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
      )
      standings = payload.standings
      syncSessionElo(payload.standings)
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
      syncSessionElo(payload.standings)
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

    void refreshSession().catch((err) => {
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
    <h1>Enigma</h1>
    <p class="subtext">Infer the problem. Ship the solution.</p>
  </header>

  <main class="layout">
    <section class="panel controls">
      {#if !sessionUser}
        <h2>Account</h2>

        <div class="switch-row auth-switch">
          <button
            type="button"
            class:active={authMode === 'register'}
            on:click={() => {
              authMode = 'register'
              error = ''
              notice = ''
            }}
          >
            Create account
          </button>
          <button
            type="button"
            class:active={authMode === 'login'}
            on:click={() => {
              authMode = 'login'
              error = ''
              notice = ''
            }}
          >
            Sign in
          </button>
        </div>

        <label>
          <span>Display name</span>
          <input bind:value={authName} maxlength="24" autocomplete="username" />
        </label>

        <label>
          <span>Password</span>
          <input
            type="password"
            bind:value={authPassword}
            minlength="6"
            autocomplete={authMode === 'login' ? 'current-password' : 'new-password'}
          />
        </label>

        <button class="primary" on:click={() => authenticate(authMode)} disabled={busy}>
          {authMode === 'register' ? 'Create Account' : 'Sign In'}
        </button>
        <p class="subtle note">No guest toggle needed. Session auth is now cookie-backed.</p>
      {:else if !inArena}
        <h2>Home</h2>
        <p class="session-chip">Signed in as {sessionUser.name}</p>
        <p class="mono">Current ELO · {sessionUser.elo}</p>

        <button
          class="primary"
          on:click={() => {
            inArena = true
            error = ''
            notice = ''
          }}
          disabled={busy}
        >
          Enter Arena
        </button>
        <button class="ghost wide" on:click={logout} disabled={busy}>Sign Out</button>
      {:else}
        <h2>Match Setup</h2>
        <p class="session-chip">{sessionUser.name} · ELO {sessionUser.elo}</p>

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
          <input
            type="number"
            bind:value={timeLimitSeconds}
            min="60"
            max="7200"
            disabled={mode === 'ranked'}
          />
        </label>

        <label>
          <span>Seed</span>
          <input type="number" bind:value={seed} />
        </label>

        <button class="primary" on:click={startMatch} disabled={busy}>
          {match ? 'Restart Match' : 'Start Match'}
        </button>
        <button
          class="ghost wide"
          on:click={() => {
            inArena = false
            error = ''
            notice = ''
          }}
          disabled={busy}
        >
          Back to Home
        </button>
        <button class="ghost wide" on:click={logout} disabled={busy}>Sign Out</button>
      {/if}

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

      {#if notice}
        <p class="notice">{notice}</p>
      {/if}
      {#if error}
        <p class="error">{error}</p>
      {/if}
    </section>

    <section class="panel arena">
      {#if !sessionUser}
        <div class="home-state">
          <h2>Landing</h2>
          <p>
            Create an account or sign in to unlock session-backed play. Your identity persists, ranked
            checks use your real account, and you can launch matches from a clean home page.
          </p>
          <ul>
            <li>Cookie-backed session auth</li>
            <li>Account create + sign in flow</li>
            <li>No guest checkbox dead-end</li>
          </ul>
        </div>
      {:else if !inArena}
        <div class="home-state">
          <h2>Welcome, {sessionUser.name}</h2>
          <p>
            You are signed in and ready. Enter the arena from the left panel when you want to generate
            a puzzle match.
          </p>
          <ul>
            <li>Current ELO: {sessionUser.elo}</li>
            <li>Ranked eligibility uses logged-in session</li>
            <li>Theme and mode controls are in Match Setup</li>
          </ul>
        </div>
      {:else if !match}
        <p class="empty">Start a match to load prompt, samples, and editor scaffold.</p>
      {:else}
        <header class="arena-head">
          <h2>{match.theme}</h2>
          <p class="mono">
            {match.mode.toUpperCase()} · {match.difficulty.toUpperCase()} · {match.time_limit_seconds}s
          </p>
        </header>

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
          <button class="ghost" on:click={testSamples} disabled={busy}>Test Samples</button>
          <button class="primary" on:click={submit} disabled={busy}>Submit</button>
          <button class="ghost" on:click={() => requestHint(1)} disabled={busy}>Hint 1</button>
          <button class="ghost" on:click={() => requestHint(2)} disabled={busy}>Hint 2</button>
          <button class="ghost" on:click={forfeit} disabled={busy}>Forfeit</button>
          <button class="ghost" on:click={finishMatch} disabled={busy}>Finish</button>
        </div>

        {#if testResult}
          <section class="judge-result">
            <p class="chip" class:ok={testResult.verdict === 'accepted'} class:bad={testResult.verdict !== 'accepted'}>
              TEST · {testResult.verdict.toUpperCase()} · SAMPLE {testResult.sample_passed}/{testResult.sample_total} · {testResult.runtime_ms}ms
            </p>
            {#if testResult.message}
              <p class="mono subtle">{testResult.message}</p>
            {/if}
            {#if testResult.stdout}
              <p class="mono subtle">Stdout</p>
              <pre class="stdout-block">{testResult.stdout}</pre>
            {/if}
          </section>
        {/if}

        {#if submitResult}
          <section class="judge-result">
            <p class="chip" class:ok={submitResult.verdict === 'accepted'} class:bad={submitResult.verdict !== 'accepted'}>
              SUBMIT · {submitResult.verdict.toUpperCase()} · SAMPLE {submitResult.sample_passed}/{submitResult.sample_total} · HIDDEN {submitResult.hidden_passed}/{submitResult.hidden_total} · {submitResult.runtime_ms}ms
            </p>
            {#if submitResult.message}
              <p class="mono subtle">{submitResult.message}</p>
            {/if}
            {#if submitResult.stdout}
              <p class="mono subtle">Stdout</p>
              <pre class="stdout-block">{submitResult.stdout}</pre>
            {/if}
            {#if submitResult.first_failed_hidden_test}
              <article class="failed-case">
                <h3>First failed hidden test</h3>
                <p><strong>Input</strong></p>
                <pre>{submitResult.first_failed_hidden_test.input_str}</pre>
                <p><strong>Expected output</strong></p>
                <pre>{submitResult.first_failed_hidden_test.expected_output}</pre>
                <p><strong>Your output</strong></p>
                <pre>{submitResult.first_failed_hidden_test.actual_output}</pre>
                <button class="ghost" on:click={promoteFailedTest} disabled={busy}>
                  Use this as sample test
                </button>
              </article>
            {/if}
          </section>
        {/if}

        {#if match.sample_tests.length >= 4}
          <p class="mono subtle">
            Visible sample limit reached (4). Promoting a new case replaces the oldest sample.
          </p>
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
