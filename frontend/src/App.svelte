<script lang="ts">
  import { onMount } from 'svelte'

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

  let busy = false
  let error = ''
  let notice = ''

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
          <textarea bind:value={code} spellcheck="false"></textarea>
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
