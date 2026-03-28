<script lang="ts">
  import { onMount, tick } from "svelte";
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import {
    bundledThemes,
    bundledThemesInfo,
    type BundledTheme,
  } from "shiki/bundle/web";

  type UiTheme = "light" | "dark";
  type AppearanceMode = UiTheme | "system";
  type View = "home" | "arena" | "leaderboard" | "settings";
  type AuthMode = "register" | "login";
  type Mode = "zen" | "casual" | "ranked";
  type Difficulty = "easy" | "medium" | "hard" | "expert";
  type ConsoleType = "info" | "system" | "success" | "error";

  type SessionUser = {
    id: string;
    name: string;
    guest: boolean;
    elo: number;
  };

  type SessionPayload = {
    authenticated: boolean;
    user?: SessionUser;
  };

  type AuthResponse = {
    user: SessionUser;
  };

  type Standing = {
    placement: number;
    user_id: string;
    name: string;
    elo: number;
    solved: boolean;
    hidden_passed: number;
    hint_level: number;
    forfeited: boolean;
    rating_delta: number;
  };

  type LeaderboardEntry = {
    placement: number;
    user_id: string;
    name: string;
    elo: number;
    guest: boolean;
  };

  type LeaderboardPayload = {
    leaderboard: LeaderboardEntry[];
    current_user: LeaderboardEntry | null;
    total_players: number;
  };

  type MatchPayload = {
    match_id: string;
    mode: Mode;
    theme: string;
    difficulty: Difficulty;
    time_limit_seconds: number;
    prompt: string;
    scaffold: string;
    sample_tests: Array<{ input: string; output: string }>;
    standings: Standing[];
  };

  type FailedHiddenTest = {
    input_str: string;
    expected_output: string;
    actual_output: string;
  };

  type JudgePayload = {
    verdict: "accepted" | "sample_failed" | "wrong_answer" | "error";
    sample_passed: number;
    sample_total: number;
    hidden_passed: number;
    hidden_total: number;
    runtime_ms: number;
    message: string;
    stdout: string;
    first_failed_hidden_test: FailedHiddenTest | null;
    sample_tests: Array<{ input: string; output: string }>;
    standings: Standing[];
  };

  type ConsoleEntry = {
    id: number;
    text: string;
    type: ConsoleType;
  };

  type ShikiThemeDefinition = {
    colors?: Record<string, string>;
    tokenColors?: Array<{
      scope?: string | string[];
      settings?: {
        foreground?: string;
      };
    }>;
  };

  type EditorThemePalette = {
    accent: string;
    bg: string;
    surface: string;
    text: string;
    mutedText: string;
    panelBorder: string;
    consoleBg: string;
    success: string;
    error: string;
    editorBg: string;
    editorText: string;
    selection: string;
    keyword: string;
    string: string;
    comment: string;
    number: string;
    functionName: string;
  };

  const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
  const FALLBACK_THEME = "String manipulation (unix-like text processing)";
  const INDENT = "    ";
  const LEADERBOARD_LIMIT = 10;
  const APPEARANCE_STORAGE_KEY = "yhack.appearance";
  const LIGHT_THEME_STORAGE_KEY = "yhack.editor-theme.light";
  const DARK_THEME_STORAGE_KEY = "yhack.editor-theme.dark";
  const DEFAULT_LIGHT_EDITOR_THEME: BundledTheme = "github-light";
  const DEFAULT_DARK_EDITOR_THEME: BundledTheme = "github-dark-default";
  const APPEARANCE_MODE_ORDER: AppearanceMode[] = ["system", "light", "dark"];
  const themeInfoById = new Map(
    bundledThemesInfo.map((theme) => [theme.id as BundledTheme, theme]),
  );

  if (!hljs.getLanguage("python")) {
    hljs.registerLanguage("python", python);
  }

  const modeOptions: Mode[] = ["zen", "casual", "ranked"];
  const difficultyOptions: Difficulty[] = ["easy", "medium", "hard", "expert"];

  let authMode: AuthMode = "register";
  let authName = "";
  let authPassword = "";

  let sessionUser: SessionUser | null = null;
  let activeView: View = "home";

  let mode: Mode = "zen";
  let difficulty: Difficulty = "easy";
  let selectedTheme = FALLBACK_THEME;
  let timeLimitSeconds = 900;

  let themePref: UiTheme = "dark";
  let appearanceMode: AppearanceMode = "system";
  let systemMatcher: MediaQueryList | null = null;
  let mediaListener: (() => void) | null = null;
  let themeStatusText = "";
  let lightEditorTheme: BundledTheme = DEFAULT_LIGHT_EDITOR_THEME;
  let darkEditorTheme: BundledTheme = DEFAULT_DARK_EDITOR_THEME;
  let activeEditorTheme: BundledTheme = DEFAULT_DARK_EDITOR_THEME;
  let activeEditorThemeName = themeInfoById.get(DEFAULT_DARK_EDITOR_THEME)?.displayName ??
    DEFAULT_DARK_EDITOR_THEME;
  let availableEditorThemes = bundledThemesInfo.filter(
    (theme) => theme.type === "dark",
  );
  let themeMenuOpen = false;
  let themeMenuEl: HTMLDivElement | null = null;

  let themes = [FALLBACK_THEME];
  let match: MatchPayload | null = null;
  let standings: Standing[] = [];
  let leaderboard: LeaderboardEntry[] = [];
  let leaderboardCurrentUser: LeaderboardEntry | null = null;
  let leaderboardTotalPlayers = 0;
  let code = "";
  let hints: string[] = [];
  let testResult: JudgePayload | null = null;
  let submitResult: JudgePayload | null = null;

  let busy = false;
  let error = "";
  let notice = "";

  let timerText = "00:00";
  let timeRemaining = 0;
  let timerInterval: ReturnType<typeof setInterval> | null = null;

  let highlightedCode = "";

  let consoleEntries: ConsoleEntry[] = [];
  let consoleNextId = 1;
  let consoleEl: HTMLDivElement | null = null;
  let highlightEl: HTMLPreElement | null = null;
  let lineNumbersEl: HTMLPreElement | null = null;
  let lineNumbers = "1";
  let editorScrollLeft = 0;

  function userInitial(name: string | undefined): string {
    return name?.trim().charAt(0).toUpperCase() || "?";
  }

  function raceModeIcon(value: Mode): string {
    if (value === "ranked") {
      return "fa-trophy";
    }
    if (value === "casual") {
      return "fa-user-friends";
    }
    return "fa-mountain";
  }

  function formatDuration(totalSeconds: number): string {
    const safe = Math.max(0, totalSeconds);
    const hours = Math.floor(safe / 3600);
    const minutes = Math.floor((safe % 3600) / 60);
    const seconds = safe % 60;
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds
        .toString()
        .padStart(2, "0")}`;
    }
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  }

  function clearTimer(): void {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function startTimer(seconds: number): void {
    clearTimer();
    timeRemaining = Math.max(0, seconds);
    timerText = formatDuration(timeRemaining);
    timerInterval = setInterval(() => {
      timeRemaining = Math.max(0, timeRemaining - 1);
      timerText = formatDuration(timeRemaining);
      if (timeRemaining <= 0) {
        clearTimer();
      }
    }, 1000);
  }

  function resetConsole(): void {
    consoleEntries = [];
    consoleNextId = 1;
    appendConsole("Sandbox environment initialized. Python 3.10.", "system");
    appendConsole("Waiting for submission...", "info");
  }

  function appendConsole(text: string, type: ConsoleType = "info"): void {
    consoleEntries = [
      ...consoleEntries,
      {
        id: consoleNextId,
        text,
        type,
      },
    ];
    consoleNextId += 1;

    void tick().then(() => {
      if (consoleEl) {
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
    });
  }

  function appendJudgeOutput(payload: JudgePayload): void {
    if (payload.stdout.trim().length > 0) {
      appendConsole(payload.stdout.trimEnd(), "info");
    }
    if (payload.message) {
      appendConsole(
        payload.message,
        payload.verdict === "accepted" ? "success" : "error",
      );
    }
  }

  function highlightPython(source: string): string {
    if (!source) {
      return "";
    }

    return hljs.highlight(source, {
      language: "python",
      ignoreIllegals: true,
    }).value;
  }

  function syncEditorScroll(event: Event): void {
    if (!highlightEl) {
      return;
    }
    const target = event.currentTarget as HTMLTextAreaElement;
    editorScrollLeft = target.scrollLeft;
    highlightEl.scrollTop = target.scrollTop;
    highlightEl.scrollLeft = target.scrollLeft;
    if (lineNumbersEl) {
      lineNumbersEl.scrollTop = target.scrollTop;
    }
  }

  function handleEditorKeydown(event: KeyboardEvent): void {
    const target = event.currentTarget as HTMLTextAreaElement;
    const { selectionStart, selectionEnd } = target;

    if (event.key === "Enter") {
      event.preventDefault();

      const beforeCursor = code.slice(0, selectionStart);
      const currentLine = beforeCursor.split("\n").at(-1) ?? "";
      const baseIndent = currentLine.match(/^[\t ]*/)?.[0] ?? "";
      const extraIndent = /:\s*(#.*)?$/.test(currentLine.trimEnd()) ? INDENT : "";
      const insertion = `\n${baseIndent}${extraIndent}`;

      code = `${code.slice(0, selectionStart)}${insertion}${code.slice(selectionEnd)}`;
      const cursor = selectionStart + insertion.length;
      void tick().then(() => {
        target.selectionStart = cursor;
        target.selectionEnd = cursor;
      });
      return;
    }

    if (event.key !== "Tab") {
      return;
    }
    event.preventDefault();

    if (selectionStart === selectionEnd) {
      code = `${code.slice(0, selectionStart)}${INDENT}${code.slice(selectionEnd)}`;
      const cursor = selectionStart + INDENT.length;
      void tick().then(() => {
        target.selectionStart = cursor;
        target.selectionEnd = cursor;
      });
      return;
    }

    const selection = code.slice(selectionStart, selectionEnd);
    const indented = `${INDENT}${selection.replace(/\n/g, `\n${INDENT}`)}`;
    code = `${code.slice(0, selectionStart)}${indented}${code.slice(selectionEnd)}`;

    void tick().then(() => {
      target.selectionStart = selectionStart;
      target.selectionEnd = selectionStart + indented.length;
    });
  }

  function showHome(): void {
    activeView = "home";
    error = "";
    notice = "";
  }

  function showArena(): void {
    if (!sessionUser) {
      activeView = "home";
      return;
    }
    activeView = "arena";
    error = "";
    notice = "";
  }

  function toggleLeaderboardView(): void {
    if (activeView === "leaderboard") {
      if (match && sessionUser) {
        showArena();
        return;
      }
      showHome();
      return;
    }
    activeView = "leaderboard";
    error = "";
    notice = "";
  }

  function showSettings(): void {
    activeView = "settings";
    error = "";
    notice = "";
  }

  function showPlayView(): void {
    if (match && sessionUser) {
      showArena();
      return;
    }
    showHome();
  }

  function resolveSystemTheme(): UiTheme {
    return systemMatcher?.matches ? "dark" : "light";
  }

  function cycleAppearanceMode(): void {
    const currentIndex = APPEARANCE_MODE_ORDER.indexOf(appearanceMode);
    const nextMode =
      APPEARANCE_MODE_ORDER[(currentIndex + 1) % APPEARANCE_MODE_ORDER.length];
    setAppearanceMode(nextMode);
  }

  function resolveAppearanceMode(mode: AppearanceMode = appearanceMode): UiTheme {
    if (mode === "system") {
      return resolveSystemTheme();
    }
    return mode;
  }

  function applyTheme(theme: UiTheme): void {
    document.documentElement.dataset.theme = theme;
  }

  function themeName(themeId: BundledTheme): string {
    return themeInfoById.get(themeId)?.displayName ?? themeId;
  }

  function buildFaviconDataUrl(color: string): string {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="enigma favicon"><text x="8" y="44" fill="${color}" font-family="'Roboto Mono','Fira Code',monospace" font-size="32" font-weight="700" letter-spacing="-1.5">&lt;/&gt;</text></svg>`;
    return `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }

  function updateFavicon(color: string): void {
    const favicon = document.getElementById("app-favicon");
    if (!(favicon instanceof HTMLLinkElement)) {
      return;
    }
    favicon.href = buildFaviconDataUrl(color);
  }

  function scopeMatches(rawScope: string | string[], target: string): boolean {
    const scopeList = Array.isArray(rawScope)
      ? rawScope
      : rawScope.split(",").map((part) => part.trim());
    return scopeList.some(
      (scope) =>
        scope === target ||
        scope.startsWith(`${target}.`) ||
        target.startsWith(`${scope}.`),
    );
  }

  function findThemeTokenColor(
    theme: ShikiThemeDefinition,
    targets: string[],
    fallback: string,
  ): string {
    const tokenColors = theme.tokenColors ?? [];
    for (let index = tokenColors.length - 1; index >= 0; index -= 1) {
      const rule = tokenColors[index];
      if (!rule.scope || !rule.settings?.foreground) {
        continue;
      }
      if (targets.some((target) => scopeMatches(rule.scope!, target))) {
        return rule.settings.foreground;
      }
    }
    return fallback;
  }

  function extractEditorThemePalette(theme: ShikiThemeDefinition): EditorThemePalette {
    const fallbackPalette =
      themePref === "dark"
        ? {
            accent: "#e2b714",
            bg: "#323437",
            surface: "#2c2e31",
            text: "#d1d0c5",
            mutedText: "#646669",
            panelBorder: "rgba(226, 183, 20, 0.12)",
            consoleBg: "#1e1e1e",
            success: "#8cc84b",
            error: "#ca4754",
            editorBg: "#323437",
            editorText: "#d1d0c5",
            selection: "rgba(226, 183, 20, 0.34)",
            keyword: "#f7768e",
            string: "#9ece6a",
            comment: "#6b7280",
            number: "#e0af68",
            functionName: "#7aa2f7",
          }
        : {
            accent: "#a86d00",
            bg: "#f3f4f6",
            surface: "#e5e7eb",
            text: "#1f2329",
            mutedText: "#63646a",
            panelBorder: "rgba(168, 109, 0, 0.14)",
            consoleBg: "#1f2329",
            success: "#2f8f4e",
            error: "#b42318",
            editorBg: "#f3f4f6",
            editorText: "#1f2329",
            selection: "rgba(168, 109, 0, 0.22)",
            keyword: "#b42318",
            string: "#2f8f4e",
            comment: "#6b7280",
            number: "#a86d00",
            functionName: "#175cd3",
          };

    return {
      accent:
        theme.colors?.["button.background"] ??
        theme.colors?.["focusBorder"] ??
        fallbackPalette.accent,
      bg:
        theme.colors?.["editor.background"] ??
        theme.colors?.["sideBar.background"] ??
        fallbackPalette.bg,
      surface:
        theme.colors?.["sideBar.background"] ??
        theme.colors?.["panel.background"] ??
        theme.colors?.["editorWidget.background"] ??
        fallbackPalette.surface,
      text:
        theme.colors?.["editor.foreground"] ?? fallbackPalette.text,
      mutedText:
        theme.colors?.["descriptionForeground"] ??
        theme.colors?.["editorLineNumber.foreground"] ??
        fallbackPalette.mutedText,
      panelBorder:
        theme.colors?.["panel.border"] ??
        theme.colors?.["editorWidget.border"] ??
        theme.colors?.["contrastBorder"] ??
        fallbackPalette.panelBorder,
      consoleBg:
        theme.colors?.["terminal.background"] ??
        theme.colors?.["editor.background"] ??
        fallbackPalette.consoleBg,
      success:
        theme.colors?.["terminal.ansiGreen"] ??
        theme.colors?.["testing.iconPassed"] ??
        fallbackPalette.success,
      error:
        theme.colors?.["terminal.ansiRed"] ??
        theme.colors?.["errorForeground"] ??
        fallbackPalette.error,
      editorBg:
        theme.colors?.["editor.background"] ?? fallbackPalette.editorBg,
      editorText:
        theme.colors?.["editor.foreground"] ?? fallbackPalette.editorText,
      selection:
        theme.colors?.["editor.selectionBackground"] ??
        fallbackPalette.selection,
      keyword: findThemeTokenColor(
        theme,
        ["keyword.control", "keyword.operator", "storage.type", "keyword"],
        fallbackPalette.keyword,
      ),
      string: findThemeTokenColor(
        theme,
        ["string", "string.quoted"],
        fallbackPalette.string,
      ),
      comment: findThemeTokenColor(
        theme,
        ["comment", "punctuation.definition.comment"],
        fallbackPalette.comment,
      ),
      number: findThemeTokenColor(
        theme,
        ["constant.numeric", "number"],
        fallbackPalette.number,
      ),
      functionName: findThemeTokenColor(
        theme,
        ["entity.name.function", "support.function", "entity.name.class"],
        fallbackPalette.functionName,
      ),
    };
  }

  async function applyEditorTheme(themeId: BundledTheme): Promise<void> {
    const moduleValue = await bundledThemes[themeId]();
    const theme = ("default" in moduleValue
      ? moduleValue.default
      : moduleValue) as ShikiThemeDefinition;
    const palette = extractEditorThemePalette(theme);
    const root = document.documentElement;

    root.style.setProperty("--main-color", palette.accent);
    root.style.setProperty("--caret-color", palette.accent);
    root.style.setProperty("--theme-accent", palette.accent);
    root.style.setProperty("--bg-color", palette.bg);
    root.style.setProperty("--sub-alt-color", palette.surface);
    root.style.setProperty("--text-color", palette.text);
    root.style.setProperty("--sub-color", palette.mutedText);
    root.style.setProperty("--panel-border", palette.panelBorder);
    root.style.setProperty("--console-bg", palette.consoleBg);
    root.style.setProperty("--success-color", palette.success);
    root.style.setProperty("--error-color", palette.error);
    root.style.setProperty("--editor-bg", palette.editorBg);
    root.style.setProperty("--editor-text", palette.editorText);
    root.style.setProperty("--editor-selection", palette.selection);
    root.style.setProperty("--editor-keyword", palette.keyword);
    root.style.setProperty("--editor-string", palette.string);
    root.style.setProperty("--editor-comment", palette.comment);
    root.style.setProperty("--editor-number", palette.number);
    root.style.setProperty("--editor-function", palette.functionName);
    updateFavicon(palette.accent);

    activeEditorTheme = themeId;
    activeEditorThemeName = themeName(themeId);
  }

  function syncThemeState(): void {
    themePref = resolveAppearanceMode();
    applyTheme(themePref);

    const nextTheme =
      themePref === "dark" ? darkEditorTheme : lightEditorTheme;
    void applyEditorTheme(nextTheme).catch((err) => {
      error = toErrorMessage(err);
    });
  }

  function setAppearanceMode(mode: AppearanceMode): void {
    appearanceMode = mode;
    localStorage.setItem(APPEARANCE_STORAGE_KEY, mode);
    syncThemeState();
  }

  function setEditorTheme(themeId: BundledTheme): void {
    const themeInfo = themeInfoById.get(themeId);
    if (!themeInfo) {
      return;
    }

    if (themeInfo.type === "light") {
      lightEditorTheme = themeId;
      localStorage.setItem(LIGHT_THEME_STORAGE_KEY, themeId);
    } else {
      darkEditorTheme = themeId;
      localStorage.setItem(DARK_THEME_STORAGE_KEY, themeId);
    }

    syncThemeState();
  }

  function toErrorMessage(value: unknown): string {
    if (value instanceof Error) {
      return value.message;
    }
    return "Unexpected error";
  }

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    const data = (await response.json().catch(() => ({}))) as {
      error?: string;
    };
    if (!response.ok) {
      throw new Error(data.error ?? `Request failed (${response.status})`);
    }
    return data as T;
  }

  async function loadThemes(): Promise<void> {
    const payload = await api<{ themes: string[] }>("/api/themes");
    if (payload.themes.length > 0) {
      themes = payload.themes;
      if (!themes.includes(selectedTheme)) {
        selectedTheme = themes[0];
      }
    }
  }

  async function loadLeaderboard(): Promise<void> {
    const payload = await api<LeaderboardPayload>(
      `/api/leaderboard?limit=${LEADERBOARD_LIMIT}`,
    );
    leaderboard = payload.leaderboard;
    leaderboardCurrentUser = payload.current_user;
    leaderboardTotalPlayers = payload.total_players;
  }

  function leaderboardPercentile(placement: number): string {
    if (leaderboardTotalPlayers <= 1) {
      return "Top 100%";
    }
    const percentile = Math.round(
      (1 - (placement - 1) / (leaderboardTotalPlayers - 1)) * 100,
    );
    return `Top ${Math.max(1, percentile)}%`;
  }

  function leaderboardRowNote(entry: LeaderboardEntry): string {
    if (entry.user_id === sessionUser?.id) {
      return "You";
    }
    if (entry.placement === 1) {
      return "Leader";
    }
    return "Ranked";
  }

  function syncSessionElo(currentStandings: Standing[]): void {
    if (!sessionUser) {
      return;
    }
    const self = currentStandings.find(
      (row) => row.user_id === sessionUser?.id,
    );
    if (self) {
      sessionUser = { ...sessionUser, elo: self.elo };
    }
  }

  async function refreshSession(): Promise<void> {
    const payload = await api<SessionPayload>("/api/auth/session");
    if (!payload.authenticated || !payload.user) {
      sessionUser = null;
      activeView = "home";
      return;
    }
    sessionUser = payload.user;
    await loadLeaderboard();
  }

  async function authenticate(nextMode: AuthMode): Promise<void> {
    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<AuthResponse>(`/api/auth/${nextMode}`, {
        method: "POST",
        body: JSON.stringify({ name: authName, password: authPassword }),
      });
      sessionUser = payload.user;
      authPassword = "";
      notice =
        nextMode === "register"
          ? "Account created. Session is active."
          : "Signed in.";
      void loadLeaderboard().catch((err) => {
        error = toErrorMessage(err);
      });
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function logout(): Promise<void> {
    busy = true;
    error = "";
    notice = "";
    try {
      await api<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
      sessionUser = null;
      activeView = "home";
      match = null;
      standings = [];
      testResult = null;
      submitResult = null;
      hints = [];
      code = "";
      clearTimer();
      timerText = "00:00";
      notice = "Signed out.";
      resetConsole();
      void loadLeaderboard().catch((err) => {
        error = toErrorMessage(err);
      });
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function startMatch(): Promise<void> {
    if (!sessionUser) {
      error = "Sign in to start a match.";
      activeView = "home";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    testResult = null;
    submitResult = null;
    hints = [];
    const requestedMode = mode;

    try {
      const party = await api<{ code: string }>("/api/parties", {
        method: "POST",
        body: JSON.stringify({
          mode,
          theme: selectedTheme,
          difficulty,
          time_limit_seconds: mode === "ranked" ? 3600 : timeLimitSeconds,
        }),
      });

      const payload = await api<MatchPayload>(
        `/api/parties/${party.code}/start`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );

      match = payload;
      mode = payload.mode;
      difficulty = payload.difficulty;
      selectedTheme = payload.theme;
      timeLimitSeconds = payload.time_limit_seconds;
      standings = payload.standings;
      syncSessionElo(payload.standings);
      code = payload.scaffold;
      activeView = "arena";

      startTimer(payload.time_limit_seconds);
      resetConsole();
      appendConsole(`Match loaded: ${payload.theme}`, "system");
      if (payload.mode !== requestedMode) {
        notice = `Mode switched to ${payload.mode.toUpperCase()} due to ranked eligibility.`;
      }
    } catch (err) {
      error = toErrorMessage(err);
      match = null;
      standings = [];
      appendConsole(`System error: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function launchConfiguredMatch(): Promise<void> {
    await startMatch();
  }

  async function startRace(nextMode: Mode): Promise<void> {
    mode = nextMode;
    await startMatch();
  }

  async function submit(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    const currentMatchId = match.match_id;
    busy = true;
    error = "";
    notice = "";

    appendConsole("> Executing submission in sandbox...", "system");

    try {
      const payload = await api<JudgePayload>(
        `/api/matches/${currentMatchId}/submit`,
        {
          method: "POST",
          body: JSON.stringify({ code }),
        },
      );

      submitResult = payload;
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests };
      }
      standings = payload.standings;
      syncSessionElo(payload.standings);

      appendConsole(
        `Submit: sample ${payload.sample_passed}/${payload.sample_total}, hidden ${payload.hidden_passed}/${payload.hidden_total}, ${payload.runtime_ms}ms`,
        payload.verdict === "accepted" ? "success" : "error",
      );
      appendJudgeOutput(payload);
      if (payload.first_failed_hidden_test) {
        appendConsole(
          "First failed hidden test available for promotion.",
          "system",
        );
      }
      if (payload.verdict === "accepted") {
        appendConsole("Match complete. Great run.", "success");
      }
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Submission failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function testSamples(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    const currentMatchId = match.match_id;
    busy = true;
    error = "";
    notice = "";

    appendConsole("> Running sample tests...", "system");

    try {
      const payload = await api<JudgePayload>(
        `/api/matches/${currentMatchId}/test`,
        {
          method: "POST",
          body: JSON.stringify({ code }),
        },
      );

      testResult = payload;
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests };
      }
      standings = payload.standings;
      syncSessionElo(payload.standings);

      appendConsole(
        `Samples: ${payload.sample_passed}/${payload.sample_total} passed (${payload.runtime_ms}ms)`,
        payload.verdict === "accepted" ? "success" : "error",
      );
      appendJudgeOutput(payload);
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Sample test failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function promoteFailedTest(): Promise<void> {
    if (!match || !sessionUser || !submitResult?.first_failed_hidden_test) {
      return;
    }
    const currentMatchId = match.match_id;
    const currentSubmit = submitResult;

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<{
        sample_tests: Array<{ input: string; output: string }>;
      }>(`/api/matches/${currentMatchId}/promote-failed-test`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (match?.match_id === currentMatchId) {
        match = { ...match, sample_tests: payload.sample_tests };
      }
      submitResult = { ...currentSubmit, first_failed_hidden_test: null };
      notice = "Promoted failed hidden test to visible samples.";
      appendConsole("Promoted failed hidden test to samples.", "system");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Promotion failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function requestHint(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    busy = true;
    error = "";
    try {
      const payload = await api<{ level: 1 | 2 | 3; hint: string }>(
        `/api/matches/${match.match_id}/hint`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      const nextHints = [...hints];
      nextHints[payload.level - 1] = payload.hint;
      hints = nextHints;
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Hint request failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function forfeit(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    busy = true;
    error = "";
    try {
      const payload = await api<{ standings: Standing[] }>(
        `/api/matches/${match.match_id}/forfeit`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      standings = payload.standings;
      syncSessionElo(payload.standings);
      appendConsole("You forfeited the match.", "error");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Forfeit failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  $: if (mode === "ranked") {
    timeLimitSeconds = 3600;
  }

  $: themeStatusText =
    appearanceMode === "system"
      ? `Following system (${themePref})`
      : `${appearanceMode} mode`;

  $: highlightedCode = highlightPython(code);
  $: lineNumbers = Array.from(
    { length: Math.max(1, code.split("\n").length) },
    (_, index) => `${index + 1}`,
  ).join("\n");
  $: availableEditorThemes = bundledThemesInfo.filter(
    (theme) => theme.type === themePref,
  );

  onMount(() => {
    const savedAppearance = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (
      savedAppearance === "light" ||
      savedAppearance === "dark" ||
      savedAppearance === "system"
    ) {
      appearanceMode = savedAppearance;
    }

    const savedLightTheme = localStorage.getItem(LIGHT_THEME_STORAGE_KEY);
    if (
      savedLightTheme &&
      themeInfoById.get(savedLightTheme as BundledTheme)?.type === "light"
    ) {
      lightEditorTheme = savedLightTheme as BundledTheme;
    }

    const savedDarkTheme = localStorage.getItem(DARK_THEME_STORAGE_KEY);
    if (
      savedDarkTheme &&
      themeInfoById.get(savedDarkTheme as BundledTheme)?.type === "dark"
    ) {
      darkEditorTheme = savedDarkTheme as BundledTheme;
    }

    systemMatcher = window.matchMedia("(prefers-color-scheme: dark)");
    syncThemeState();

    mediaListener = () => {
      if (appearanceMode === "system") {
        syncThemeState();
      }
    };
    systemMatcher.addEventListener("change", mediaListener);

    const handlePointerDown = (event: PointerEvent) => {
      if (!themeMenuOpen || !themeMenuEl) {
        return;
      }
      const target = event.target;
      if (target instanceof Node && !themeMenuEl.contains(target)) {
        themeMenuOpen = false;
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);

    resetConsole();

    void loadThemes().catch((err) => {
      error = toErrorMessage(err);
    });

    void loadLeaderboard().catch((err) => {
      error = toErrorMessage(err);
    });

    void refreshSession().catch((err) => {
      error = toErrorMessage(err);
    });

    return () => {
      clearTimer();
      if (systemMatcher && mediaListener) {
        systemMatcher.removeEventListener("change", mediaListener);
      }
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  });
</script>

<div id="app-shell">
  <header>
    <button type="button" class="logo" on:click={showHome}>
      <i class="fas fa-code icon" aria-hidden="true"></i>
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
        <i class="fas fa-keyboard" aria-hidden="true"></i>
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
      <button type="button" class="nav-icon" title="Info">
        <i class="fas fa-info" aria-hidden="true"></i>
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
          on:click={() => {
            themeMenuOpen = !themeMenuOpen;
          }}
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
    </nav>
  </header>

  {#if activeView === "home"}
    <main id="home-view">
      <div class="hero-text">
        Infer the hidden rule. Write the Python snippet.<br />
        <span>Defeat your opponents.</span>
      </div>

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
                  error = "";
                  notice = "";
                }}
              >
                Create account
              </button>
              <button
                type="button"
                class:active={authMode === "login"}
                on:click={() => {
                  authMode = "login";
                  error = "";
                  notice = "";
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
                <select bind:value={mode}>
                  {#each modeOptions as option}
                    <option value={option}>{option.toUpperCase()}</option>
                  {/each}
                </select>
              </label>

              <label>
                <span>Puzzle theme</span>
                <select bind:value={selectedTheme} disabled={mode === "ranked"}>
                  {#each themes as theme}
                    <option value={theme}>{theme}</option>
                  {/each}
                </select>
              </label>

              <label>
                <span>Difficulty</span>
                <select bind:value={difficulty} disabled={mode === "ranked"}>
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
                  disabled={mode === "ranked"}
                />
              </label>

            </div>

            <div class="home-actions">
              <button
                type="button"
                class="btn primary"
                on:click={launchConfiguredMatch}
                disabled={busy}
              >
                {match ? "Restart Match" : "Start Match"}
              </button>

              <button
                type="button"
                class="btn"
                on:click={() => {
                  if (match) {
                    showArena();
                  }
                }}
                disabled={!match || busy}
              >
                Resume Race
              </button>

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
  {:else if activeView === "leaderboard"}
    <main id="leaderboard-view">
      <aside class="leaderboard-sidebar">
        <section class="leaderboard-filter-card">
          <p class="eyebrow">Ranked ladder</p>
          <button type="button" class="leaderboard-filter active">
            <i class="fas fa-globe" aria-hidden="true"></i>
            all-time elo
          </button>
        </section>

        <section class="leaderboard-filter-card">
          <p class="eyebrow">Overview</p>
          <div class="leaderboard-stat">
            <span>Players</span>
            <strong>{leaderboardTotalPlayers}</strong>
          </div>
          <div class="leaderboard-stat">
            <span>Your rank</span>
            <strong
              >{leaderboardCurrentUser
                ? `#${leaderboardCurrentUser.placement}`
                : "Unranked"}</strong
            >
          </div>
          <div class="leaderboard-stat">
            <span>Your ELO</span>
            <strong
              >{leaderboardCurrentUser
                ? leaderboardCurrentUser.elo
                : "-"}</strong
            >
          </div>
        </section>
      </aside>

      <section class="leaderboard-main">
        <div class="leaderboard-title-row">
          <div>
            <p class="eyebrow">All-time</p>
            <h1>Ranked Leaderboard</h1>
          </div>
          <span class="leaderboard-badge">{leaderboardTotalPlayers} players</span>
        </div>

        <div class="leaderboard-meta">
          <span>Showing the top ranked players by ELO.</span>
          <button type="button" class="btn" on:click={() => void loadLeaderboard()}>
            Refresh
          </button>
        </div>

        {#if leaderboard.length === 0}
          <section class="leaderboard-empty-state">
            <h2>Leaderboard</h2>
            <p>Registered players will appear here once ranked runs are completed.</p>
          </section>
        {:else}
          <div class="leaderboard-table-wrap">
            <div class="leaderboard-table leaderboard-table-head" role="presentation">
              <span>#</span>
              <span>player</span>
              <span>elo</span>
              <span>percentile</span>
              <span>status</span>
            </div>

            <div class="leaderboard-table-body">
              {#each leaderboard as row}
                <article
                  class="leaderboard-table leaderboard-table-row"
                  class:current={row.user_id === sessionUser?.id}
                >
                  <span class="leaderboard-cell rank">
                    {#if row.placement === 1}
                      <i class="fas fa-crown" aria-hidden="true"></i>
                    {/if}
                    {row.placement}
                  </span>
                  <span class="leaderboard-cell player">
                    <strong>{row.name}</strong>
                  </span>
                  <span class="leaderboard-cell score">{row.elo}</span>
                  <span class="leaderboard-cell percentile">
                    {leaderboardPercentile(row.placement)}
                  </span>
                  <span class="leaderboard-cell note">
                    {leaderboardRowNote(row)}
                  </span>
                </article>
              {/each}
            </div>
          </div>
        {/if}
      </section>
    </main>
  {:else if activeView === "settings"}
    <main id="settings-view">
      <aside class="settings-sidebar">
        <section class="settings-nav-card">
          <p class="eyebrow">Workspace</p>
          <h1>Settings</h1>
          <p class="settings-sidebar-copy">
            Tune the arena, editor, and account surface so the app matches your
            workflow.
          </p>

          <div class="settings-summary-list">
            <div class="settings-summary-item">
              <span>Session</span>
              <strong>{sessionUser ? sessionUser.name : "Guest mode"}</strong>
            </div>
            <div class="settings-summary-item">
              <span>Appearance</span>
              <strong>{themeStatusText}</strong>
            </div>
            <div class="settings-summary-item">
              <span>Editor theme</span>
              <strong>{activeEditorThemeName}</strong>
            </div>
          </div>

          <nav class="settings-section-nav" aria-label="Settings sections">
            <a href="#settings-profile" class="settings-section-link">
              <i class="fas fa-id-badge" aria-hidden="true"></i>
              <span>Profile</span>
            </a>
            <a href="#settings-arena" class="settings-section-link">
              <i class="fas fa-sliders" aria-hidden="true"></i>
              <span>Arena Defaults</span>
            </a>
            <a href="#settings-editor" class="settings-section-link">
              <i class="fas fa-palette" aria-hidden="true"></i>
              <span>Editor Theme</span>
            </a>
            <a href="#settings-system" class="settings-section-link">
              <i class="fas fa-server" aria-hidden="true"></i>
              <span>System</span>
            </a>
          </nav>

          <button type="button" class="btn primary wide" on:click={showPlayView}>
            Back to Play
          </button>
        </section>
      </aside>

      <section class="settings-main">
        <div class="settings-title-row">
          <div>
            <p class="eyebrow">Configuration</p>
            <h2>Workspace Control Panel</h2>
            <p class="settings-title-copy">
              Inspired by the reference mockup, but rebuilt in Enigma's native
              terminal-first style.
            </p>
          </div>
          <span class="leaderboard-badge">Local settings</span>
        </div>

        <section id="settings-profile" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">Profile</p>
              <h3>Pilot Identity</h3>
            </div>
            <span class="settings-panel-note">
              {sessionUser ? "Connected account" : "Offline preview"}
            </span>
          </div>

          <div class="settings-profile-grid">
            <article class="settings-identity-card">
              <div class="settings-avatar" aria-hidden="true">
                {userInitial(sessionUser?.name)}
              </div>
              <div class="settings-identity-copy">
                <strong>{sessionUser?.name ?? "Guest challenger"}</strong>
                <span>
                  {sessionUser
                    ? `Current ladder rating: ${sessionUser.elo} ELO`
                    : "Sign in to persist ranked progress and match history."}
                </span>
              </div>
            </article>

            <div class="settings-stat-grid">
              <div class="settings-stat-card">
                <span>Account state</span>
                <strong>{sessionUser ? "Authenticated" : "Guest"}</strong>
              </div>
              <div class="settings-stat-card">
                <span>Leaderboard rank</span>
                <strong>
                  {leaderboardCurrentUser
                    ? `#${leaderboardCurrentUser.placement}`
                    : "Unranked"}
                </strong>
              </div>
              <div class="settings-stat-card">
                <span>Active match</span>
                <strong>{match ? match.mode.toUpperCase() : "None"}</strong>
              </div>
              <div class="settings-stat-card">
                <span>Visible themes</span>
                <strong>{themes.length}</strong>
              </div>
            </div>
          </div>

          <div class="settings-action-row">
            {#if sessionUser}
              <button type="button" class="btn" on:click={logout} disabled={busy}>
                <i class="fas fa-right-from-bracket" aria-hidden="true"></i>
                Sign Out
              </button>
            {/if}
            <button
              type="button"
              class="btn"
              on:click={() => void refreshSession()}
              disabled={busy}
            >
              <i class="fas fa-arrows-rotate" aria-hidden="true"></i>
              Refresh Session
            </button>
          </div>
        </section>

        <section id="settings-arena" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">Arena</p>
              <h3>Match Defaults</h3>
            </div>
            <span class="settings-panel-note">Used the next time you queue</span>
          </div>

          <div class="settings-mode-grid" role="group" aria-label="Default mode">
            {#each modeOptions as option}
              <button
                type="button"
                class="settings-mode-card"
                class:active={mode === option}
                on:click={() => {
                  mode = option;
                }}
              >
                <i class={`fas ${raceModeIcon(option)}`} aria-hidden="true"></i>
                <strong>{option.toUpperCase()}</strong>
                <span>
                  {option === "zen"
                    ? "Solo practice with no pressure."
                    : option === "casual"
                      ? "Share a link and customize the room."
                      : "Backend-governed queue with rating changes."}
                </span>
              </button>
            {/each}
          </div>

          <div class="field-grid">
            <label>
              <span>Difficulty</span>
              <select bind:value={difficulty}>
                {#each difficultyOptions as option}
                  <option value={option}>{option.toUpperCase()}</option>
                {/each}
              </select>
            </label>

            <label>
              <span>Puzzle Theme</span>
              <select bind:value={selectedTheme} disabled={mode === "ranked"}>
                {#each themes as theme}
                  <option value={theme}>{theme}</option>
                {/each}
              </select>
            </label>

            <label>
              <span>Timer (seconds)</span>
              <input
                type="number"
                bind:value={timeLimitSeconds}
                min="60"
                max="7200"
                disabled={mode === "ranked"}
              />
            </label>
          </div>

          <p class="settings-helper-copy">
            Ranked still locks time to 3600 seconds and lets the backend choose
            the valid puzzle configuration.
          </p>
        </section>

        <section id="settings-editor" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">Editor</p>
              <h3>Appearance & Theme</h3>
            </div>
            <span class="settings-panel-note">{themePref} mode live preview</span>
          </div>

          <div class="settings-editor-grid">
            <article class="settings-control-card">
              <div class="settings-control-group">
                <span class="eyebrow">Appearance mode</span>
                <div class="segmented">
                  {#each APPEARANCE_MODE_ORDER as option}
                    <button
                      type="button"
                      class:active={appearanceMode === option}
                      on:click={() => setAppearanceMode(option)}
                    >
                      {option}
                    </button>
                  {/each}
                </div>
              </div>

              <label>
                <span>{themePref} theme palette</span>
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
              </label>

              <div class="settings-action-row">
                <button type="button" class="btn" on:click={cycleAppearanceMode}>
                  <i class="fas fa-circle-half-stroke" aria-hidden="true"></i>
                  Cycle Appearance
                </button>
                <button
                  type="button"
                  class="btn"
                  on:click={() => {
                    themeMenuOpen = true;
                  }}
                >
                  <i class="fas fa-swatchbook" aria-hidden="true"></i>
                  Open Header Palette
                </button>
              </div>
            </article>

            <article class="settings-preview-card">
              <div class="settings-preview-labels">
                <span>{themeStatusText}</span>
                <strong>{activeEditorThemeName}</strong>
              </div>
              <div class="settings-code-preview" aria-hidden="true">
                <pre><span class="preview-keyword">def</span> <span class="preview-function">solve</span>(line):
    <span class="preview-keyword">return</span> <span class="preview-string">line</span>.strip()[::<span class="preview-number">-1</span>]  <span class="preview-comment"># hidden-rule ready</span></pre>
              </div>
            </article>
          </div>
        </section>

        <section id="settings-system" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">System</p>
              <h3>Frontend & Backend Snapshot</h3>
            </div>
            <span class="settings-panel-note">Quick health checks</span>
          </div>

          <div class="settings-system-grid">
            <div class="settings-stat-card">
              <span>API target</span>
              <strong>{API_BASE || "Same origin"}</strong>
            </div>
            <div class="settings-stat-card">
              <span>Leaderboard rows</span>
              <strong>{leaderboard.length}</strong>
            </div>
            <div class="settings-stat-card">
              <span>Current screen</span>
              <strong>{activeView}</strong>
            </div>
            <div class="settings-stat-card">
              <span>Busy state</span>
              <strong>{busy ? "Working" : "Idle"}</strong>
            </div>
          </div>

          <div class="settings-action-row">
            <button
              type="button"
              class="btn"
              on:click={() => void loadThemes()}
              disabled={busy}
            >
              <i class="fas fa-brush" aria-hidden="true"></i>
              Reload Themes
            </button>
            <button
              type="button"
              class="btn"
              on:click={() => void loadLeaderboard()}
              disabled={busy}
            >
              <i class="fas fa-ranking-star" aria-hidden="true"></i>
              Refresh Leaderboard
            </button>
            <button
              type="button"
              class="btn primary"
              on:click={launchConfiguredMatch}
              disabled={!sessionUser || busy}
            >
              <i class="fas fa-bolt" aria-hidden="true"></i>
              Launch With Defaults
            </button>
          </div>
        </section>
      </section>
    </main>
  {:else}
    <main id="race-view">
      {#if !sessionUser}
        <section class="race-empty">
          <p>Sign in to start a match.</p>
          <button type="button" class="btn primary" on:click={showHome}
            >Back Home</button
          >
        </section>
      {:else if !match}
        <section class="race-empty">
          <p>
            Start a match from Home to load samples and the editor scaffold.
          </p>
          <button type="button" class="btn" on:click={showHome}
            >Back Home</button
          >
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
                <div class="samples-grid">
                  <span class="sample-head">Sample Input</span>
                  <span class="sample-head">Sample Output</span>
                  {#each match.sample_tests as sample}
                    <pre class="sample-cell">{sample.input}</pre>
                    <pre class="sample-cell">{sample.output}</pre>
                  {/each}
                </div>
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
              <div class="editor-container">
                <div class="editor-stack">
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
                  on:keydown={handleEditorKeydown}
                  on:scroll={syncEditorScroll}
                ></textarea>
              </div>

              <div class="editor-actions">
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
            <button type="button" class="btn" on:click={showHome}
              >Back Home</button
            >
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
                    >{row.rating_delta >= 0 ? "+" : ""}{row.rating_delta}</span
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
  {/if}

  <footer>
    <div class="footer-left">
      <a href="https://github.com/jdwl-7321/yhack-2026"
        ><i class="fas fa-code-branch" aria-hidden="true"></i> github</a
      >
    </div>
    <div class="footer-right">
      <span
        ><i class="fas fa-palette" aria-hidden="true"></i> {appearanceMode ===
        "system"
          ? `system ${themePref} · ${activeEditorThemeName}`
          : `${appearanceMode} · ${activeEditorThemeName}`}</span
      >
      <span
        ><i class="fas fa-code-branch" aria-hidden="true"></i> v0.1.0-alpha</span
      >
    </div>
  </footer>
</div>
