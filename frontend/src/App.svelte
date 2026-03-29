<script lang="ts">
  import { onMount, tick } from "svelte";
  import { basicSetup, EditorView } from "codemirror";
  import { keymap } from "@codemirror/view";
  import { python as cmPython } from "@codemirror/lang-python";
  import { vim } from "@replit/codemirror-vim";
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import {
    bundledThemes,
    bundledThemesInfo,
    type BundledTheme,
  } from "shiki/bundle/web";

  type UiTheme = "light" | "dark";
  type AppearanceMode = UiTheme | "system";
  type View = "home" | "arena" | "leaderboard" | "postmatch" | "settings";
  type KeybindMode = "normal" | "vim" | "custom";
  type VimMode = "insert" | "normal";
  type EditorAction = "submit" | "test" | "hint" | "forfeit";
  type EditorFontSize = "compact" | "default" | "large";
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
    party_code: string;
    mode: Mode;
    finished: boolean;
    theme: string;
    difficulty: Difficulty;
    time_limit_seconds: number;
    created_at: number;
    prompt: string;
    scaffold: string;
    sample_tests: Array<{ input: string; output: string }>;
    standings: Standing[];
  };

  type PartySettingsPayload = {
    theme: string;
    difficulty: Difficulty;
    time_limit_seconds: number;
    seed: number | null;
  };

  type PartyPayload = {
    code: string;
    join_code: string;
    join_path: string;
    mode: Mode;
    leader_id: string;
    member_limit: number;
    is_full: boolean;
    active_match_id: string | null;
    active_match_finished: boolean | null;
    settings: PartySettingsPayload;
    members: SessionUser[];
    invite_link: string;
  };

  type PostMatchState = {
    reason: string;
    mode: Mode;
    theme: string;
    difficulty: Difficulty;
    time_limit_seconds: number;
    standings: Standing[];
  };

  type LiveStatusTone = "neutral" | "ok" | "warn";

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

  type EditorSnapshot = {
    value: string;
    selectionStart: number;
    selectionEnd: number;
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

  type AccountOutcome = "solved" | "forfeit";

  type AccountRecentRun = {
    match_id: string;
    mode: Mode;
    theme: string;
    difficulty: Difficulty;
    outcome: AccountOutcome;
    hidden_passed: number;
    rating_delta: number;
    at: string;
  };

  type AccountStats = {
    matchesStarted: number;
    matchesSolved: number;
    rankedFinished: number;
    rankedWins: number;
    hintsUsed: number;
    sampleRuns: number;
    submissions: number;
    forfeits: number;
    bestHiddenPassed: number;
    recentRuns: AccountRecentRun[];
    recordedMatchIds: string[];
  };

  const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
  const FALLBACK_THEME = "String manipulation (unix-like text processing)";
  const INDENT = "    ";
  const LEADERBOARD_LIMIT = 10;
  const PARTY_LIMIT_MIN = 2;
  const PARTY_LIMIT_MAX = 16;
  const DEFAULT_PARTY_LIMIT = 4;
  const APPEARANCE_STORAGE_KEY = "yhack.appearance";
  const LIGHT_THEME_STORAGE_KEY = "yhack.editor-theme.light";
  const DARK_THEME_STORAGE_KEY = "yhack.editor-theme.dark";
  const KEYBIND_MODE_STORAGE_KEY = "yhack.keybind-mode";
  const CUSTOM_SHORTCUTS_STORAGE_KEY = "yhack.custom-shortcuts";
  const EDITOR_FONT_SIZE_STORAGE_KEY = "yhack.editor-font-size";
  const ACCOUNT_STATS_STORAGE_PREFIX = "yhack.account-stats";
  const DEFAULT_LIGHT_EDITOR_THEME: BundledTheme = "github-light";
  const DEFAULT_DARK_EDITOR_THEME: BundledTheme = "github-dark-default";
  const APPEARANCE_MODE_ORDER: AppearanceMode[] = ["system", "light", "dark"];
  const ACCOUNT_RECENT_RUN_LIMIT = 6;
  const ACCOUNT_RECORDED_MATCH_LIMIT = 30;
  const DEFAULT_CUSTOM_SHORTCUTS: Record<EditorAction, string> = {
    submit: "s",
    test: "r",
    hint: "h",
    forfeit: "f",
  };
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
  let partyLimit = DEFAULT_PARTY_LIMIT;
  let joinCodeInput = "";
  let party: PartyPayload | null = null;

  let themePref: UiTheme = "dark";
  let appearanceMode: AppearanceMode = "system";
  let systemMatcher: MediaQueryList | null = null;
  let mediaListener: (() => void) | null = null;
  let themeStatusText = "";
  let lightEditorTheme: BundledTheme = DEFAULT_LIGHT_EDITOR_THEME;
  let darkEditorTheme: BundledTheme = DEFAULT_DARK_EDITOR_THEME;
  let activeEditorTheme: BundledTheme = DEFAULT_DARK_EDITOR_THEME;
  let keybindMode: KeybindMode = "normal";
  let vimMode: VimMode = "insert";
  let vimPendingKey = "";
  let customShortcuts: Record<EditorAction, string> = {
    ...DEFAULT_CUSTOM_SHORTCUTS,
  };
  let customShortcutError = "";
  let editorFontSize: EditorFontSize = "default";
  let activeEditorThemeName = themeInfoById.get(DEFAULT_DARK_EDITOR_THEME)?.displayName ??
    DEFAULT_DARK_EDITOR_THEME;
  let availableEditorThemes = bundledThemesInfo.filter(
    (theme) => theme.type === "dark",
  );
  let themeMenuOpen = false;
  let themeMenuEl: HTMLDivElement | null = null;
  let accountMenuOpen = false;
  let accountMenuEl: HTMLDivElement | null = null;

  let themes = [FALLBACK_THEME];
  let match: MatchPayload | null = null;
  let postMatch: PostMatchState | null = null;
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
  let timerExpiredHandled = false;
  let liveSocket: WebSocket | null = null;
  let liveSocketReady = false;
  let liveSocketRetryTimer: ReturnType<typeof setTimeout> | null = null;
  let liveSocketSubscribedChannels = new Set<string>();

  let highlightedCode = "";

  let consoleEntries: ConsoleEntry[] = [];
  let consoleNextId = 1;
  let consoleEl: HTMLDivElement | null = null;
  let highlightEl: HTMLPreElement | null = null;
  let accountStats: AccountStats = emptyAccountStats();
  let accountLeaderboardEntry: LeaderboardEntry | null = null;
  let accountSolveRate: number | null = null;
  let accountRankLabel = "Unranked";
  let accountPercentileLabel = "No ranked result yet";
  let accountRankedWinLabel = "0/0";

  function emptyAccountStats(): AccountStats {
    return {
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
  }

  function accountStatsStorageKey(userId: string): string {
    return `${ACCOUNT_STATS_STORAGE_PREFIX}:${userId}`;
  }

  function normalizeAccountStats(raw: unknown): AccountStats {
    const fallback = emptyAccountStats();
    if (!raw || typeof raw !== "object") {
      return fallback;
    }

    const source = raw as Partial<AccountStats>;
    const recentRuns = Array.isArray(source.recentRuns)
      ? source.recentRuns
          .filter(
            (run): run is AccountRecentRun =>
              !!run &&
              typeof run === "object" &&
              typeof run.match_id === "string" &&
              typeof run.mode === "string" &&
              typeof run.theme === "string" &&
              typeof run.difficulty === "string" &&
              (run.outcome === "solved" || run.outcome === "forfeit") &&
              typeof run.hidden_passed === "number" &&
              typeof run.rating_delta === "number" &&
              typeof run.at === "string",
          )
          .slice(0, ACCOUNT_RECENT_RUN_LIMIT)
      : [];

    const recordedMatchIds = Array.isArray(source.recordedMatchIds)
      ? source.recordedMatchIds
          .filter((value): value is string => typeof value === "string")
          .slice(0, ACCOUNT_RECORDED_MATCH_LIMIT)
      : [];

    return {
      matchesStarted: typeof source.matchesStarted === "number"
        ? source.matchesStarted
        : fallback.matchesStarted,
      matchesSolved: typeof source.matchesSolved === "number"
        ? source.matchesSolved
        : fallback.matchesSolved,
      rankedFinished: typeof source.rankedFinished === "number"
        ? source.rankedFinished
        : fallback.rankedFinished,
      rankedWins: typeof source.rankedWins === "number"
        ? source.rankedWins
        : fallback.rankedWins,
      hintsUsed: typeof source.hintsUsed === "number"
        ? source.hintsUsed
        : fallback.hintsUsed,
      sampleRuns: typeof source.sampleRuns === "number"
        ? source.sampleRuns
        : fallback.sampleRuns,
      submissions: typeof source.submissions === "number"
        ? source.submissions
        : fallback.submissions,
      forfeits: typeof source.forfeits === "number"
        ? source.forfeits
        : fallback.forfeits,
      bestHiddenPassed: typeof source.bestHiddenPassed === "number"
        ? source.bestHiddenPassed
        : fallback.bestHiddenPassed,
      recentRuns,
      recordedMatchIds,
    };
  }

  function loadAccountStats(user: SessionUser): void {
    const saved = localStorage.getItem(accountStatsStorageKey(user.id));
    if (!saved) {
      accountStats = emptyAccountStats();
      return;
    }

    try {
      accountStats = normalizeAccountStats(JSON.parse(saved));
    } catch {
      accountStats = emptyAccountStats();
    }
  }

  function persistAccountStats(): void {
    if (!sessionUser) {
      return;
    }
    localStorage.setItem(
      accountStatsStorageKey(sessionUser.id),
      JSON.stringify(accountStats),
    );
  }

  function updateAccountStats(mutator: (current: AccountStats) => AccountStats): void {
    if (!sessionUser) {
      return;
    }
    accountStats = normalizeAccountStats(mutator(accountStats));
    persistAccountStats();
  }

  function currentStanding(rows: Standing[]): Standing | null {
    const user = sessionUser;
    if (!user) {
      return null;
    }
    return rows.find((row) => row.user_id === user.id) ?? null;
  }

  function recordCompletedMatch(outcome: AccountOutcome, rows: Standing[]): void {
    const currentMatch = match;
    if (!sessionUser || !currentMatch) {
      return;
    }

    const self = currentStanding(rows);
    if (!self || accountStats.recordedMatchIds.includes(currentMatch.match_id)) {
      return;
    }

    updateAccountStats((current) => ({
      ...current,
      matchesSolved: current.matchesSolved + (outcome === "solved" ? 1 : 0),
      rankedFinished:
        current.rankedFinished + (currentMatch.mode === "ranked" ? 1 : 0),
      rankedWins:
        current.rankedWins +
        (currentMatch.mode === "ranked" && outcome === "solved" ? 1 : 0),
      forfeits: current.forfeits + (outcome === "forfeit" ? 1 : 0),
      bestHiddenPassed: Math.max(current.bestHiddenPassed, self.hidden_passed),
      recentRuns: [
        {
          match_id: currentMatch.match_id,
          mode: currentMatch.mode,
          theme: currentMatch.theme,
          difficulty: currentMatch.difficulty,
          outcome,
          hidden_passed: self.hidden_passed,
          rating_delta: self.rating_delta,
          at: new Date().toISOString(),
        },
        ...current.recentRuns.filter(
          (run) => run.match_id !== currentMatch.match_id,
        ),
      ].slice(0, ACCOUNT_RECENT_RUN_LIMIT),
      recordedMatchIds: [currentMatch.match_id, ...current.recordedMatchIds].slice(
        0,
        ACCOUNT_RECORDED_MATCH_LIMIT,
      ),
    }));
  }

  function buildPostMatchState(reason: string, rows: Standing[]): PostMatchState | null {
    if (!match) {
      return null;
    }

    return {
      reason,
      mode: match.mode,
      theme: match.theme,
      difficulty: match.difficulty,
      time_limit_seconds: match.time_limit_seconds,
      standings: rows,
    };
  }

  function showPostMatch(reason: string, rows: Standing[]): void {
    const outcome = currentStanding(rows)?.solved ? "solved" : "forfeit";
    recordCompletedMatch(outcome, rows);

    const nextPostMatch = buildPostMatchState(reason, rows);
    if (!nextPostMatch) {
      return;
    }

    postMatch = nextPostMatch;
    standings = rows;
    clearTimer();
    setLiveStatus("Post-match board ready", "ok");
    activeView = "postmatch";
  }

  function postMatchWinner(rows: Standing[]): Standing | null {
    return rows.length > 0 ? rows[0] : null;
  }

  function postMatchSolvedCount(rows: Standing[]): number {
    return rows.filter((row) => row.solved).length;
  }

  function postMatchForfeitCount(rows: Standing[]): number {
    return rows.filter((row) => row.forfeited).length;
  }

  function setLiveStatus(text: string, tone: LiveStatusTone = "neutral"): void {
    liveStatusText = text;
    liveStatusTone = tone;
  }

  function websocketBaseUrl(): string {
    if (typeof window === "undefined") {
      return "ws://localhost:5000";
    }

    const apiUrl = API_BASE
      ? new URL(API_BASE, window.location.origin)
      : new URL(window.location.origin);
    const protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${apiUrl.host}`;
  }

  function liveSocketUrl(): string {
    return `${websocketBaseUrl()}/ws/events`;
  }

  function desiredLiveChannels(): Set<string> {
    const channels = new Set<string>();
    if (party) {
      channels.add(`party:${party.code}`);
    }
    if (match) {
      channels.add(`match:${match.match_id}`);
    }
    return channels;
  }

  function clearLiveSocketRetry(): void {
    if (liveSocketRetryTimer) {
      clearTimeout(liveSocketRetryTimer);
      liveSocketRetryTimer = null;
    }
  }

  function sendLiveSocketMessage(payload: Record<string, string>): void {
    if (!liveSocket || liveSocket.readyState !== WebSocket.OPEN) {
      return;
    }
    liveSocket.send(JSON.stringify(payload));
  }

  function disconnectLiveSocket(): void {
    clearLiveSocketRetry();
    liveSocketSubscribedChannels = new Set();
    liveSocketReady = false;
    if (liveSocket) {
      try {
        liveSocket.close();
      } catch {
        // ignore close errors
      }
      liveSocket = null;
    }
  }

  function scheduleLiveSocketReconnect(): void {
    if (liveSocketRetryTimer || !sessionUser || (!party && !match)) {
      return;
    }
    liveSocketRetryTimer = setTimeout(() => {
      liveSocketRetryTimer = null;
      connectLiveSocket();
    }, 1000);
  }

  function syncLiveSocketSubscriptions(): void {
    if (!liveSocketReady || !liveSocket) {
      return;
    }

    const desired = desiredLiveChannels();
    for (const channel of Array.from(liveSocketSubscribedChannels)) {
      if (!desired.has(channel)) {
        sendLiveSocketMessage({ action: "unsubscribe", channel });
        liveSocketSubscribedChannels.delete(channel);
      }
    }
    for (const channel of desired) {
      if (!liveSocketSubscribedChannels.has(channel)) {
        sendLiveSocketMessage({ action: "subscribe", channel });
        liveSocketSubscribedChannels.add(channel);
      }
    }
  }

  async function handleLivePartyUpdate(
    nextParty: PartyPayload,
    eventName: string,
  ): Promise<void> {
    const user = sessionUser;
    if (!user) {
      return;
    }

    const previousParty = party;
    const stillMember = nextParty.members.some((member) => member.id === user.id);
    if (!stillMember) {
      if (previousParty && previousParty.code === nextParty.code) {
        party = null;
        joinCodeInput = "";
        setLiveStatus("You were removed from the party", "warn");
        notice = "You were removed from the party.";
      }
      return;
    }

    applyParty(nextParty);

    if (previousParty) {
      if (nextParty.members.length > previousParty.members.length) {
        setLiveStatus("A new member joined", "ok");
      } else if (nextParty.members.length < previousParty.members.length) {
        setLiveStatus("A member left or was kicked", "warn");
      }
    }

    if (eventName === "settings_updated") {
      setLiveStatus("Host updated party setup", "ok");
    }

    if (nextParty.active_match_id && (!match || match.match_id !== nextParty.active_match_id)) {
      setLiveStatus("Host started the match", "ok");
      await openMatchFromLobby(nextParty.active_match_id);
    }
  }

  async function handleLiveMatchUpdate(
    nextMatch: MatchPayload,
    eventName: string,
  ): Promise<void> {
    if (!sessionUser) {
      return;
    }

    if (!match || match.match_id !== nextMatch.match_id) {
      if (party && party.active_match_id === nextMatch.match_id && !nextMatch.finished) {
        await openMatchFromLobby(nextMatch.match_id);
      }
      return;
    }

    const previous = match;
    match = {
      ...nextMatch,
      scaffold: previous.scaffold,
      sample_tests: previous.sample_tests,
    };
    standings = nextMatch.standings;
    syncSessionElo(nextMatch.standings);

    if (nextMatch.finished) {
      setLiveStatus("Match finished", "ok");
      showPostMatch("Match complete", nextMatch.standings);
      return;
    }

    if (eventName === "submission") {
      setLiveStatus("Standings updated from a submission", "ok");
    }
    if (eventName === "forfeit") {
      setLiveStatus("A player forfeited", "warn");
    }
  }

  function handleLiveSocketMessage(raw: string): void {
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }

    const type = payload.type;
    if (type === "party.updated" && payload.party) {
      void handleLivePartyUpdate(
        payload.party as PartyPayload,
        String(payload.event ?? "updated"),
      );
      return;
    }

    if (type === "match.updated" && payload.match) {
      void handleLiveMatchUpdate(
        payload.match as MatchPayload,
        String(payload.event ?? "updated"),
      );
      return;
    }
  }

  function connectLiveSocket(): void {
    if (!sessionUser) {
      return;
    }

    if (liveSocket && (liveSocket.readyState === WebSocket.OPEN || liveSocket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    clearLiveSocketRetry();
    const ws = new WebSocket(liveSocketUrl());
    liveSocket = ws;

    ws.addEventListener("open", () => {
      if (liveSocket !== ws) {
        return;
      }
      liveSocketReady = true;
      syncLiveSocketSubscriptions();
      sendLiveSocketMessage({ action: "ping", channel: "" });
    });

    ws.addEventListener("message", (event) => {
      handleLiveSocketMessage(String(event.data));
    });

    ws.addEventListener("close", () => {
      if (liveSocket !== ws) {
        return;
      }
      liveSocket = null;
      liveSocketReady = false;
      liveSocketSubscribedChannels = new Set();
      if (sessionUser && (party || match)) {
        setLiveStatus("Reconnecting live channel...", "warn");
        scheduleLiveSocketReconnect();
      }
    });
  }

  function syncLiveSocket(): void {
    if (!sessionUser || (!party && !match)) {
      disconnectLiveSocket();
      return;
    }

    connectLiveSocket();
    syncLiveSocketSubscriptions();
  }
  let lineNumbersEl: HTMLPreElement | null = null;
  let lineNumbers = "1";
  let editorScrollLeft = 0;
  let vimEditorHostEl: HTMLDivElement | null = null;
  let vimEditorView: EditorView | null = null;
  let editorHistory: EditorSnapshot[] = [
    { value: "", selectionStart: 0, selectionEnd: 0 },
  ];
  let editorHistoryIndex = 0;
  let applyingEditorHistory = false;
  let passwordCurrent = "";
  let passwordNext = "";
  let passwordConfirm = "";
  let passwordBusy = false;
  let passwordNotice = "";
  let passwordError = "";

  function userInitial(name: string | undefined): string {
    return name?.trim().charAt(0).toUpperCase() || "?";
  }
  let isPartyMode = false;
  let isPartyLeader = false;
  let canEditPartySetup = true;
  let liveStatusText = "Idle";
  let liveStatusTone: LiveStatusTone = "neutral";

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
    timerExpiredHandled = false;
  }

  function startTimer(seconds: number): void {
    clearTimer();
    timeRemaining = Math.max(0, seconds);
    timerText = formatDuration(timeRemaining);
    timerExpiredHandled = false;
    if (timeRemaining <= 0) {
      timerExpiredHandled = true;
      void finishMatch("Time limit reached");
      return;
    }
    timerInterval = setInterval(() => {
      timeRemaining = Math.max(0, timeRemaining - 1);
      timerText = formatDuration(timeRemaining);
      if (timeRemaining <= 0) {
        clearTimer();
        if (!timerExpiredHandled) {
          timerExpiredHandled = true;
          void finishMatch("Time limit reached");
        }
      }
    }, 1000);
  }

  function remainingSecondsForMatch(payload: MatchPayload): number {
    const elapsed = Math.floor(Date.now() / 1000 - payload.created_at);
    return Math.max(0, payload.time_limit_seconds - elapsed);
  }

  async function finishMatch(reason: string): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }

    try {
      const payload = await api<{ standings: Standing[] }>(
        `/api/matches/${match.match_id}/finish`,
        {
          method: "POST",
          body: JSON.stringify({ user_id: sessionUser.id }),
        },
      );
      syncSessionElo(payload.standings);
      setLiveStatus("Match finished", "ok");
      showPostMatch(reason, payload.standings);
    } catch (err) {
      error = toErrorMessage(err);
    }
  }

  async function openMatchFromLobby(matchId: string): Promise<void> {
    const payload = await api<MatchPayload>(`/api/matches/${matchId}`);
    match = payload;
    postMatch = null;
    testResult = null;
    submitResult = null;
    hints = [];
    standings = payload.standings;
    mode = payload.mode;
    difficulty = payload.difficulty;
    selectedTheme = payload.theme;
    timeLimitSeconds = payload.time_limit_seconds;
    syncSessionElo(payload.standings);

    if (payload.finished) {
      showPostMatch("Match complete", payload.standings);
      return;
    }

    activeView = "arena";
    startTimer(remainingSecondsForMatch(payload));
    code = payload.scaffold;
    resetConsole();
    setLiveStatus("Match started", "ok");
    appendConsole(`Joined live match: ${payload.theme}`, "system");
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

  function setEditorSelection(
    target: HTMLTextAreaElement,
    start: number,
    end = start,
  ): void {
    const nextStart = Math.max(0, Math.min(start, code.length));
    const nextEnd = Math.max(0, Math.min(end, code.length));
    void tick().then(() => {
      target.selectionStart = nextStart;
      target.selectionEnd = nextEnd;
    });
  }

  function pushEditorSnapshot(snapshot: EditorSnapshot): void {
    const current = editorHistory[editorHistoryIndex];
    if (
      current &&
      current.value === snapshot.value &&
      current.selectionStart === snapshot.selectionStart &&
      current.selectionEnd === snapshot.selectionEnd
    ) {
      return;
    }

    editorHistory = [...editorHistory.slice(0, editorHistoryIndex + 1), snapshot];
    if (editorHistory.length > 200) {
      editorHistory = editorHistory.slice(editorHistory.length - 200);
    }
    editorHistoryIndex = editorHistory.length - 1;
  }

  function resetEditorHistory(
    value: string,
    selectionStart = 0,
    selectionEnd = selectionStart,
  ): void {
    editorHistory = [{ value, selectionStart, selectionEnd }];
    editorHistoryIndex = 0;
  }

  function applyEditorChange(
    target: HTMLTextAreaElement,
    value: string,
    selectionStart: number,
    selectionEnd = selectionStart,
  ): void {
    code = value;
    pushEditorSnapshot({ value, selectionStart, selectionEnd });
    setEditorSelection(target, selectionStart, selectionEnd);
  }

  function restoreEditorSnapshot(
    target: HTMLTextAreaElement,
    snapshot: EditorSnapshot,
  ): void {
    applyingEditorHistory = true;
    code = snapshot.value;
    void tick().then(() => {
      target.selectionStart = snapshot.selectionStart;
      target.selectionEnd = snapshot.selectionEnd;
      applyingEditorHistory = false;
    });
  }

  function undoEditorChange(target: HTMLTextAreaElement): void {
    if (editorHistoryIndex <= 0) {
      return;
    }
    editorHistoryIndex -= 1;
    restoreEditorSnapshot(target, editorHistory[editorHistoryIndex]);
  }

  function redoEditorChange(target: HTMLTextAreaElement): void {
    if (editorHistoryIndex >= editorHistory.length - 1) {
      return;
    }
    editorHistoryIndex += 1;
    restoreEditorSnapshot(target, editorHistory[editorHistoryIndex]);
  }

  function handleEditorInput(event: Event): void {
    if (applyingEditorHistory) {
      return;
    }
    const target = event.currentTarget as HTMLTextAreaElement;
    const value = target.value;
    code = value;
    pushEditorSnapshot({
      value,
      selectionStart: target.selectionStart,
      selectionEnd: target.selectionEnd,
    });
  }

  function lineBounds(source: string, position: number): {
    start: number;
    end: number;
  } {
    const safePosition = Math.max(0, Math.min(position, source.length));
    const start = source.lastIndexOf("\n", Math.max(0, safePosition - 1)) + 1;
    const nextBreak = source.indexOf("\n", safePosition);
    const end = nextBreak === -1 ? source.length : nextBreak;
    return { start, end };
  }

  function insertIndentedNewline(target: HTMLTextAreaElement): void {
    const { selectionStart, selectionEnd } = target;
    const beforeCursor = code.slice(0, selectionStart);
    const currentLine = beforeCursor.split("\n").at(-1) ?? "";
    const baseIndent = currentLine.match(/^[\t ]*/)?.[0] ?? "";
    const extraIndent = /:\s*(#.*)?$/.test(currentLine.trimEnd()) ? INDENT : "";
    const insertion = `\n${baseIndent}${extraIndent}`;
    const nextCode =
      `${code.slice(0, selectionStart)}${insertion}${code.slice(selectionEnd)}`;
    const cursor = selectionStart + insertion.length;
    applyEditorChange(target, nextCode, cursor);
  }

  function indentSelection(target: HTMLTextAreaElement): void {
    const { selectionStart, selectionEnd } = target;
    if (selectionStart === selectionEnd) {
      const nextCode =
        `${code.slice(0, selectionStart)}${INDENT}${code.slice(selectionEnd)}`;
      const cursor = selectionStart + INDENT.length;
      applyEditorChange(target, nextCode, cursor);
      return;
    }

    const selection = code.slice(selectionStart, selectionEnd);
    const indented = `${INDENT}${selection.replace(/\n/g, `\n${INDENT}`)}`;
    const nextCode =
      `${code.slice(0, selectionStart)}${indented}${code.slice(selectionEnd)}`;
    applyEditorChange(
      target,
      nextCode,
      selectionStart,
      selectionStart + indented.length,
    );
  }

  function moveCaretVertical(
    target: HTMLTextAreaElement,
    direction: -1 | 1,
  ): void {
    const anchor = target.selectionStart;
    const current = lineBounds(code, anchor);
    const column = anchor - current.start;
    if (direction === -1) {
      if (current.start === 0) {
        setEditorSelection(target, 0);
        return;
      }
      const previous = lineBounds(code, current.start - 1);
      setEditorSelection(target, Math.min(previous.start + column, previous.end));
      return;
    }

    if (current.end >= code.length) {
      setEditorSelection(target, code.length);
      return;
    }
    const next = lineBounds(code, current.end + 1);
    setEditorSelection(target, Math.min(next.start + column, next.end));
  }

  function moveCaretHorizontal(
    target: HTMLTextAreaElement,
    direction: -1 | 1,
  ): void {
    const anchor = direction < 0 ? target.selectionStart : target.selectionEnd;
    setEditorSelection(target, anchor + direction);
  }

  function moveCaretToLineEdge(
    target: HTMLTextAreaElement,
    edge: "start" | "end",
  ): void {
    const bounds = lineBounds(code, target.selectionStart);
    setEditorSelection(target, edge === "start" ? bounds.start : bounds.end);
  }

  function isWordCharacter(value: string | undefined): boolean {
    return !!value && /[A-Za-z0-9_]/.test(value);
  }

  function moveCaretToNextWord(target: HTMLTextAreaElement): void {
    let cursor = target.selectionEnd;
    while (cursor < code.length && isWordCharacter(code[cursor])) {
      cursor += 1;
    }
    while (cursor < code.length && !isWordCharacter(code[cursor])) {
      cursor += 1;
    }
    setEditorSelection(target, cursor);
  }

  function moveCaretToPreviousWord(target: HTMLTextAreaElement): void {
    let cursor = Math.max(0, target.selectionStart - 1);
    while (cursor > 0 && !isWordCharacter(code[cursor])) {
      cursor -= 1;
    }
    while (cursor > 0 && isWordCharacter(code[cursor - 1])) {
      cursor -= 1;
    }
    setEditorSelection(target, cursor);
  }

  function deleteCharacterUnderCursor(target: HTMLTextAreaElement): void {
    const { selectionStart, selectionEnd } = target;
    if (selectionStart !== selectionEnd) {
      const nextCode = `${code.slice(0, selectionStart)}${code.slice(selectionEnd)}`;
      applyEditorChange(target, nextCode, selectionStart);
      return;
    }
    if (selectionStart >= code.length) {
      return;
    }
    const nextCode =
      `${code.slice(0, selectionStart)}${code.slice(selectionStart + 1)}`;
    applyEditorChange(target, nextCode, selectionStart);
  }

  function deleteCurrentLine(target: HTMLTextAreaElement): void {
    const bounds = lineBounds(code, target.selectionStart);
    const deleteEnd = bounds.end < code.length ? bounds.end + 1 : bounds.end;
    const nextCode = `${code.slice(0, bounds.start)}${code.slice(deleteEnd)}`;
    applyEditorChange(target, nextCode, Math.min(bounds.start, nextCode.length));
  }

  function openLineBelow(target: HTMLTextAreaElement): void {
    const bounds = lineBounds(code, target.selectionEnd);
    const currentLine = code.slice(bounds.start, bounds.end);
    const baseIndent = currentLine.match(/^[\t ]*/)?.[0] ?? "";
    const insertion = `\n${baseIndent}`;
    const nextCode =
      `${code.slice(0, bounds.end)}${insertion}${code.slice(bounds.end)}`;
    vimMode = "insert";
    applyEditorChange(target, nextCode, bounds.end + insertion.length);
  }

  function handleEditorActionShortcut(event: KeyboardEvent): boolean {
    if (event.metaKey) {
      return false;
    }

    if (keybindMode === "custom") {
      if (!event.altKey || event.ctrlKey || event.shiftKey) {
        return false;
      }
      const pressedKey = normalizeShortcutKey(event.key);
      const action = (
        Object.keys(customShortcuts) as EditorAction[]
      ).find((candidate) => customShortcuts[candidate] === pressedKey);
      if (!action) {
        return false;
      }
      event.preventDefault();
      void triggerEditorAction(action);
      return true;
    }

    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void triggerEditorAction(event.shiftKey ? "test" : "submit");
      return true;
    }

    if (event.altKey && !event.ctrlKey && !event.shiftKey) {
      const pressedKey = normalizeShortcutKey(event.key);
      if (pressedKey === "h") {
        event.preventDefault();
        void triggerEditorAction("hint");
        return true;
      }
      if (pressedKey === "f") {
        event.preventDefault();
        void triggerEditorAction("forfeit");
        return true;
      }
    }

    return false;
  }

  function handleEditorUndoRedoShortcut(
    event: KeyboardEvent,
    target: HTMLTextAreaElement,
  ): boolean {
    const pressedKey = event.key.toLowerCase();

    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      if (pressedKey === "z" && !event.shiftKey) {
        event.preventDefault();
        undoEditorChange(target);
        if (keybindMode === "vim") {
          vimMode = "normal";
          vimPendingKey = "";
        }
        return true;
      }

      if (
        (pressedKey === "z" && event.shiftKey) ||
        (pressedKey === "y" && !event.shiftKey)
      ) {
        event.preventDefault();
        redoEditorChange(target);
        if (keybindMode === "vim") {
          vimMode = "normal";
          vimPendingKey = "";
        }
        return true;
      }
    }

    return false;
  }

  function handleDefaultEditorKeydown(
    event: KeyboardEvent,
    target: HTMLTextAreaElement,
  ): boolean {
    if (event.key === "Enter") {
      event.preventDefault();
      insertIndentedNewline(target);
      return true;
    }

    if (event.key === "Tab") {
      event.preventDefault();
      indentSelection(target);
      return true;
    }

    return false;
  }

  function handleVimEditorKeydown(
    event: KeyboardEvent,
    target: HTMLTextAreaElement,
  ): boolean {
    if (vimMode === "insert") {
      if (event.key === "Escape") {
        event.preventDefault();
        vimMode = "normal";
        vimPendingKey = "";
        return true;
      }
      return handleDefaultEditorKeydown(event, target);
    }

    if (event.ctrlKey && !event.altKey && !event.metaKey) {
      if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        vimPendingKey = "";
        redoEditorChange(target);
        return true;
      }
      return false;
    }

    if (event.altKey || event.ctrlKey || event.metaKey) {
      return false;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      vimPendingKey = "";
      return true;
    }

    if (event.key === "i") {
      event.preventDefault();
      vimPendingKey = "";
      vimMode = "insert";
      return true;
    }

    if (event.key === "a") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretHorizontal(target, 1);
      vimMode = "insert";
      return true;
    }

    if (event.key === "o") {
      event.preventDefault();
      vimPendingKey = "";
      openLineBelow(target);
      return true;
    }

    if (event.key === "h") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretHorizontal(target, -1);
      return true;
    }

    if (event.key === "j") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretVertical(target, 1);
      return true;
    }

    if (event.key === "k") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretVertical(target, -1);
      return true;
    }

    if (event.key === "l") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretHorizontal(target, 1);
      return true;
    }

    if (event.key === "0") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretToLineEdge(target, "start");
      return true;
    }

    if (event.key === "$") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretToLineEdge(target, "end");
      return true;
    }

    if (event.key === "w") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretToNextWord(target);
      return true;
    }

    if (event.key === "b") {
      event.preventDefault();
      vimPendingKey = "";
      moveCaretToPreviousWord(target);
      return true;
    }

    if (event.key === "x") {
      event.preventDefault();
      vimPendingKey = "";
      deleteCharacterUnderCursor(target);
      return true;
    }

    if (event.key === "d") {
      event.preventDefault();
      if (vimPendingKey === "d") {
        vimPendingKey = "";
        deleteCurrentLine(target);
      } else {
        vimPendingKey = "d";
      }
      return true;
    }

    if (event.key === "u") {
      event.preventDefault();
      vimPendingKey = "";
      undoEditorChange(target);
      return true;
    }

    vimPendingKey = "";
    if (
      event.key.length === 1 ||
      event.key === "Backspace" ||
      event.key === "Enter" ||
      event.key === "Tab"
    ) {
      event.preventDefault();
      return true;
    }

    return false;
  }

  function handleEditorKeydown(event: KeyboardEvent): void {
    if (handleEditorActionShortcut(event)) {
      return;
    }
    const target = event.currentTarget as HTMLTextAreaElement;
    handleDefaultEditorKeydown(event, target);
  }

  function showHome(): void {
    activeView = "home";
    error = "";
    notice = "";
    if (!party) {
      setLiveStatus("Idle", "neutral");
    }
    accountMenuOpen = false;
  }

  function showArena(): void {
    if (!sessionUser) {
      activeView = "home";
      return;
    }
    activeView = "arena";
    error = "";
    notice = "";
    setLiveStatus("Live match in progress", "ok");
    accountMenuOpen = false;
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
    accountMenuOpen = false;
  }

  function toggleThemeMenu(): void {
    themeMenuOpen = !themeMenuOpen;
    if (themeMenuOpen) {
      accountMenuOpen = false;
    }
  }

  function toggleAccountMenu(): void {
    accountMenuOpen = !accountMenuOpen;
    if (accountMenuOpen) {
      themeMenuOpen = false;
    }
  }

  function showSettings(): void {
    activeView = "settings";
    error = "";
    notice = "";
    accountMenuOpen = false;
    themeMenuOpen = false;
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

  function accountInitials(name: string): string {
    return name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "EN";
  }

  function formatRatingDelta(value: number): string {
    return `${value >= 0 ? "+" : ""}${value}`;
  }

  function formatActivityTime(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  }

  function buildFaviconDataUrl(color: string): string {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="enigma favicon"><text x="8" y="44" fill="${color}" font-family="'Roboto Mono','Fira Code',monospace" font-size="32" font-weight="700" letter-spacing="-1.5">&lt;?&gt;</text></svg>`;
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

  function setKeybindMode(mode: KeybindMode): void {
    keybindMode = mode;
    localStorage.setItem(KEYBIND_MODE_STORAGE_KEY, mode);
  }

  function normalizeShortcutKey(raw: string): string {
    const normalized = raw.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
    return normalized.slice(-1);
  }

  function persistCustomShortcuts(): void {
    localStorage.setItem(
      CUSTOM_SHORTCUTS_STORAGE_KEY,
      JSON.stringify(customShortcuts),
    );
  }

  function setCustomShortcut(action: EditorAction, rawValue: string): void {
    const normalized = normalizeShortcutKey(rawValue);
    if (!normalized) {
      return;
    }

    const conflict = Object.entries(customShortcuts).find(
      ([existingAction, key]) => existingAction !== action && key === normalized,
    );
    if (conflict) {
      customShortcutError =
        `Alt+${normalized.toUpperCase()} is already assigned to ${conflict[0]}.`;
      return;
    }

    customShortcutError = "";
    customShortcuts = {
      ...customShortcuts,
      [action]: normalized,
    };
    persistCustomShortcuts();
  }

  function setEditorFontSize(size: EditorFontSize): void {
    editorFontSize = size;
    localStorage.setItem(EDITOR_FONT_SIZE_STORAGE_KEY, size);
  }

  function editorFontSizeLabel(size: EditorFontSize = editorFontSize): string {
    if (size === "compact") {
      return "Compact";
    }
    if (size === "large") {
      return "Large";
    }
    return "Default";
  }

  function customShortcutLabel(action: EditorAction): string {
    return `Alt+${customShortcuts[action].toUpperCase()}`;
  }

  async function triggerEditorAction(action: EditorAction): Promise<void> {
    if (action === "submit") {
      await submit();
      return;
    }
    if (action === "test") {
      await testSamples();
      return;
    }
    if (action === "hint") {
      await requestHint();
      return;
    }
    await forfeit();
  }

  function createVimActionKeymap() {
    return keymap.of([
      {
        key: "Ctrl-Enter",
        run: () => {
          void triggerEditorAction("submit");
          return true;
        },
      },
      {
        key: "Shift-Ctrl-Enter",
        run: () => {
          void triggerEditorAction("test");
          return true;
        },
      },
      {
        key: "Alt-h",
        run: () => {
          void triggerEditorAction("hint");
          return true;
        },
      },
      {
        key: "Alt-f",
        run: () => {
          void triggerEditorAction("forfeit");
          return true;
        },
      },
    ]);
  }

  function destroyVimEditor(): void {
    if (!vimEditorView) {
      return;
    }
    vimEditorView.destroy();
    vimEditorView = null;
  }

  function initializeVimEditor(): void {
    if (!vimEditorHostEl || vimEditorView) {
      return;
    }

    vimEditorView = new EditorView({
      doc: code,
      extensions: [
        vim(),
        basicSetup,
        cmPython(),
        createVimActionKeymap(),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            code = update.state.doc.toString();
          }
        }),
      ],
      parent: vimEditorHostEl,
    });
  }

  function syncVimEditorDoc(): void {
    if (!vimEditorView) {
      return;
    }
    const currentDoc = vimEditorView.state.doc.toString();
    if (currentDoc === code) {
      return;
    }
    vimEditorView.dispatch({
      changes: { from: 0, to: currentDoc.length, insert: code },
    });
  }

  function toErrorMessage(value: unknown): string {
    if (value instanceof Error) {
      return value.message;
    }
    return "Unexpected error";
  }

  function normalizePartyCode(raw: string): string {
    return raw
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "")
      .slice(0, 6);
  }

  function applyParty(partyPayload: PartyPayload): void {
    party = partyPayload;
    mode = partyPayload.mode;
    selectedTheme = partyPayload.settings.theme;
    difficulty = partyPayload.settings.difficulty;
    timeLimitSeconds = partyPayload.settings.time_limit_seconds;
    partyLimit = partyPayload.member_limit;
  }

  function partyJoinUrl(partyPayload: PartyPayload): string {
    if (typeof window === "undefined") {
      return partyPayload.join_path;
    }
    return `${window.location.origin}${partyPayload.join_path}`;
  }

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      cache: "no-store",
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
      accountStats = emptyAccountStats();
      accountMenuOpen = false;
      activeView = "home";
      match = null;
      postMatch = null;
      party = null;
      clearTimer();
      disconnectLiveSocket();
      return;
    }
    sessionUser = payload.user;
    loadAccountStats(payload.user);
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
      loadAccountStats(payload.user);
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
      accountStats = emptyAccountStats();
      accountMenuOpen = false;
      activeView = "home";
      match = null;
      postMatch = null;
      party = null;
      joinCodeInput = "";
      standings = [];
      testResult = null;
      submitResult = null;
      hints = [];
      code = "";
      resetEditorHistory("");
      clearTimer();
      disconnectLiveSocket();
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

  async function changePassword(): Promise<void> {
    if (!sessionUser || sessionUser.guest) {
      passwordError = "Sign in with a registered account to change your password.";
      return;
    }
    if (passwordNext.length < 6) {
      passwordError = "New password must be at least 6 characters.";
      passwordNotice = "";
      return;
    }
    if (passwordNext !== passwordConfirm) {
      passwordError = "New password and confirmation must match.";
      passwordNotice = "";
      return;
    }

    passwordBusy = true;
    passwordError = "";
    passwordNotice = "";
    try {
      await api<{ ok: boolean }>("/api/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: passwordCurrent,
          new_password: passwordNext,
        }),
      });
      passwordCurrent = "";
      passwordNext = "";
      passwordConfirm = "";
      passwordNotice = "Password updated.";
    } catch (err) {
      passwordError = toErrorMessage(err);
    } finally {
      passwordBusy = false;
    }
  }

  async function createPartyLobby(): Promise<void> {
    if (!sessionUser) {
      error = "Sign in to create a party.";
      activeView = "home";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>("/api/parties", {
        method: "POST",
        body: JSON.stringify({
          leader_id: sessionUser.id,
          mode,
          theme: selectedTheme,
          difficulty,
          time_limit_seconds: mode === "ranked" ? 3600 : timeLimitSeconds,
          member_limit: mode === "zen"
            ? 1
            : Math.min(
                PARTY_LIMIT_MAX,
                Math.max(PARTY_LIMIT_MIN, partyLimit),
              ),
        }),
      });

      applyParty(payload);
      setLiveStatus("Party live. Waiting for members...", "neutral");
      syncLiveSocket();
      notice = `Party created. Share code ${payload.join_code}.`;
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function refreshPartyLobby(): Promise<void> {
    const user = sessionUser;
    if (!party || !user) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(`/api/parties/${party.code}?t=${Date.now()}`);
      const stillMember = payload.members.some((member) => member.id === user.id);
      if (!stillMember) {
        party = null;
        joinCodeInput = "";
        setLiveStatus("You were removed from the party", "warn");
        notice = "You were removed from the party.";
        return;
      }

      applyParty(payload);
      setLiveStatus("Lobby synced", "ok");
      if (payload.active_match_id && (!match || match.match_id !== payload.active_match_id)) {
        setLiveStatus("Host started the match", "ok");
        await openMatchFromLobby(payload.active_match_id);
        return;
      }
      notice = "Party refreshed.";
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function joinPartyLobby(): Promise<void> {
    if (!sessionUser) {
      error = "Sign in to join a party.";
      activeView = "home";
      return;
    }

    const normalized = normalizePartyCode(joinCodeInput);
    if (!normalized) {
      error = "Enter a valid party code.";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(`/api/parties/${normalized}/join`, {
        method: "POST",
        body: JSON.stringify({ user_id: sessionUser.id }),
      });
      applyParty(payload);
      joinCodeInput = payload.join_code;
      setLiveStatus("Joined lobby. Waiting for host...", "neutral");
      syncLiveSocket();
      notice = `Joined party ${payload.join_code}.`;
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function copyPartyInvite(): Promise<void> {
    if (!party) {
      return;
    }

    const shareText = `${party.join_code} (${partyJoinUrl(party)})`;
    try {
      await navigator.clipboard.writeText(shareText);
      notice = "Join code copied to clipboard.";
    } catch {
      notice = `Join code: ${shareText}`;
    }
  }

  async function updatePartyLimit(): Promise<void> {
    if (!party || !sessionUser || party.leader_id !== sessionUser.id) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(`/api/parties/${party.code}/limit`, {
        method: "POST",
        body: JSON.stringify({
          user_id: sessionUser.id,
          member_limit: Math.min(
            PARTY_LIMIT_MAX,
            Math.max(PARTY_LIMIT_MIN, partyLimit),
          ),
        }),
      });
      applyParty(payload);
      setLiveStatus(`Party limit set to ${payload.member_limit}`, "ok");
      notice = `Party limit set to ${payload.member_limit}.`;
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function updatePartySetup(): Promise<void> {
    if (!party || !sessionUser || party.leader_id !== sessionUser.id) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(
        `/api/parties/${party.code}/settings`,
        {
          method: "POST",
          body: JSON.stringify({
            user_id: sessionUser.id,
            theme: selectedTheme,
            difficulty,
            time_limit_seconds: timeLimitSeconds,
          }),
        },
      );
      applyParty(payload);
      setLiveStatus("Party setup updated", "ok");
      notice = "Party setup updated.";
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function kickPartyMember(memberId: string): Promise<void> {
    if (!party || !sessionUser || party.leader_id !== sessionUser.id) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(`/api/parties/${party.code}/kick`, {
        method: "POST",
        body: JSON.stringify({ user_id: sessionUser.id, member_id: memberId }),
      });
      applyParty(payload);
      setLiveStatus("Member removed", "warn");
      notice = "Member removed from party.";
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  function clearPartyLobby(): void {
    party = null;
    joinCodeInput = "";
    syncLiveSocket();
    setLiveStatus("Idle", "neutral");
    notice = "Lobby closed.";
  }

  async function startMatch(partyCode?: string): Promise<void> {
    if (!sessionUser) {
      error = "Sign in to start a match.";
      activeView = "home";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    postMatch = null;
    testResult = null;
    submitResult = null;
    hints = [];
    const requestedMode = mode;

    try {
      let codeToStart = partyCode;
      if (!codeToStart) {
        const createdParty = await api<PartyPayload>("/api/parties", {
          method: "POST",
          body: JSON.stringify({
            leader_id: sessionUser.id,
            mode,
            theme: selectedTheme,
            difficulty,
            time_limit_seconds: mode === "ranked" ? 3600 : timeLimitSeconds,
            member_limit: mode === "zen" ? 1 : partyLimit,
          }),
        });
        codeToStart = createdParty.code;
        if (mode !== "zen") {
          applyParty(createdParty);
        }
      }

      const payload = await api<MatchPayload>(
        `/api/parties/${codeToStart}/start`,
        {
          method: "POST",
          body: JSON.stringify({ user_id: sessionUser.id }),
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
      resetEditorHistory(payload.scaffold);
      activeView = "arena";
      setLiveStatus("Live match in progress", "ok");
      updateAccountStats((current) => ({
        ...current,
        matchesStarted: current.matchesStarted + 1,
      }));

      if (payload.mode === "zen") {
        party = null;
      }

      startTimer(remainingSecondsForMatch(payload));
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
    if (mode === "zen") {
      party = null;
      await startMatch();
      return;
    }

    if (!party) {
      await createPartyLobby();
      return;
    }

    if (party.leader_id !== sessionUser?.id) {
      error = "Only the party leader can start the match.";
      return;
    }

    await startMatch(party.code);
  }

  async function startRace(nextMode: Mode): Promise<void> {
    if (party && party.mode !== nextMode) {
      party = null;
      setLiveStatus("Idle", "neutral");
    }
    mode = nextMode;
    if (nextMode === "casual" || nextMode === "ranked") {
      setLiveStatus("Pick create or join to go live", "neutral");
      notice = "Create a party or enter a join code to continue.";
    } else {
      setLiveStatus("Solo mode", "neutral");
      notice = "";
    }
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
      updateAccountStats((current) => ({
        ...current,
        submissions: current.submissions + 1,
        bestHiddenPassed: Math.max(current.bestHiddenPassed, payload.hidden_passed),
      }));
      appendJudgeOutput(payload);
      if (payload.first_failed_hidden_test) {
        appendConsole(
          "First failed hidden test available for promotion.",
          "system",
        );
      }
      if (payload.verdict === "accepted") {
        recordCompletedMatch("solved", payload.standings);
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
      updateAccountStats((current) => ({
        ...current,
        sampleRuns: current.sampleRuns + 1,
        bestHiddenPassed: Math.max(current.bestHiddenPassed, payload.hidden_passed),
      }));

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
      updateAccountStats((current) => ({
        ...current,
        hintsUsed: current.hintsUsed + 1,
      }));
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
      recordCompletedMatch("forfeit", payload.standings);
      appendConsole("You forfeited the match.", "error");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Forfeit failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  $: isPartyMode = mode === "casual" || mode === "ranked";
  $: isPartyLeader = !!party && !!sessionUser && party.leader_id === sessionUser.id;
  $: canEditPartySetup = !party || (isPartyLeader && mode === "casual");
  $: {
    sessionUser;
    party;
    match;
    activeView;
    syncLiveSocket();
  }

  $: if (mode === "ranked") {
    timeLimitSeconds = 3600;
  }

  $: if (isPartyMode) {
    partyLimit = Math.min(PARTY_LIMIT_MAX, Math.max(PARTY_LIMIT_MIN, partyLimit));
  } else {
    partyLimit = 1;
  }

  $: themeStatusText =
    appearanceMode === "system"
      ? `Following system (${themePref})`
      : `${appearanceMode} mode`;

  $: accountLeaderboardEntry =
    leaderboardCurrentUser ??
    leaderboard.find((entry) => entry.user_id === sessionUser?.id) ??
    null;
  $: accountSolveRate =
    accountStats.matchesStarted > 0
      ? Math.round((accountStats.matchesSolved / accountStats.matchesStarted) * 100)
      : null;
  $: accountRankLabel = accountLeaderboardEntry
    ? `#${accountLeaderboardEntry.placement}`
    : "Unranked";
  $: accountPercentileLabel = accountLeaderboardEntry
    ? leaderboardPercentile(accountLeaderboardEntry.placement)
    : "No ranked result yet";
  $: accountRankedWinLabel =
    accountStats.rankedFinished > 0
      ? `${accountStats.rankedWins}/${accountStats.rankedFinished}`
      : "0/0";

  $: highlightedCode = highlightPython(code);
  $: lineNumbers = Array.from(
    { length: Math.max(1, code.split("\n").length) },
    (_, index) => `${index + 1}`,
  ).join("\n");
  $: availableEditorThemes = bundledThemesInfo.filter(
    (theme) => theme.type === themePref,
  );
  $: if (keybindMode === "vim" && vimEditorHostEl) {
    code;
    initializeVimEditor();
    syncVimEditorDoc();
  }
  $: if (keybindMode !== "vim") {
    destroyVimEditor();
  }

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

    const savedKeybindMode = localStorage.getItem(KEYBIND_MODE_STORAGE_KEY);
    if (
      savedKeybindMode === "normal" ||
      savedKeybindMode === "vim" ||
      savedKeybindMode === "custom"
    ) {
      keybindMode = savedKeybindMode;
    }

    const savedCustomShortcuts = localStorage.getItem(CUSTOM_SHORTCUTS_STORAGE_KEY);
    if (savedCustomShortcuts) {
      try {
        const parsed = JSON.parse(savedCustomShortcuts) as Partial<
          Record<EditorAction, string>
        >;
        customShortcuts = {
          submit: normalizeShortcutKey(
            parsed.submit ?? DEFAULT_CUSTOM_SHORTCUTS.submit,
          ) || DEFAULT_CUSTOM_SHORTCUTS.submit,
          test: normalizeShortcutKey(parsed.test ?? DEFAULT_CUSTOM_SHORTCUTS.test) ||
            DEFAULT_CUSTOM_SHORTCUTS.test,
          hint: normalizeShortcutKey(parsed.hint ?? DEFAULT_CUSTOM_SHORTCUTS.hint) ||
            DEFAULT_CUSTOM_SHORTCUTS.hint,
          forfeit: normalizeShortcutKey(
            parsed.forfeit ?? DEFAULT_CUSTOM_SHORTCUTS.forfeit,
          ) || DEFAULT_CUSTOM_SHORTCUTS.forfeit,
        };
      } catch {
        customShortcuts = { ...DEFAULT_CUSTOM_SHORTCUTS };
      }
    }

    const savedEditorFontSize = localStorage.getItem(EDITOR_FONT_SIZE_STORAGE_KEY);
    if (
      savedEditorFontSize === "compact" ||
      savedEditorFontSize === "default" ||
      savedEditorFontSize === "large"
    ) {
      editorFontSize = savedEditorFontSize;
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
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (themeMenuOpen && themeMenuEl && !themeMenuEl.contains(target)) {
        themeMenuOpen = false;
      }
      if (accountMenuOpen && accountMenuEl && !accountMenuEl.contains(target)) {
        accountMenuOpen = false;
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);

    const queryCode = normalizePartyCode(
      new URL(window.location.href).searchParams.get("join") ?? "",
    );
    const pathCode = normalizePartyCode(
      window.location.pathname.match(/^\/join\/([A-Za-z0-9]+)/)?.[1] ?? "",
    );
    const initialJoinCode = queryCode || pathCode;
    if (initialJoinCode) {
      joinCodeInput = initialJoinCode;
      mode = "casual";
      notice = `Ready to join party ${initialJoinCode}. Sign in and click Join Party.`;
    }

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
      disconnectLiveSocket();
      destroyVimEditor();
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
                <div class="account-avatar">{accountInitials(sessionUser.name)}</div>
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
                      <strong>{match ? `${match.mode} · ${timerText}` : "No active match"}</strong>
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
                  disabled={!match || busy}
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
                <select bind:value={mode} disabled={!!party || busy}>
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
                  min={isPartyMode ? PARTY_LIMIT_MIN : 1}
                  max={isPartyMode ? PARTY_LIMIT_MAX : 1}
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
            {/if}

            <div class="home-actions">
              <button
                type="button"
                class="btn primary"
                on:click={launchConfiguredMatch}
                disabled={busy || (isPartyMode && !!party && !isPartyLeader)}
              >
                {#if mode === "zen"}
                  {match ? "Restart Match" : "Start Match"}
                {:else if !party}
                  Create Party
                {:else if !isPartyLeader}
                  Waiting for Leader
                {:else}
                  Start Party Match
                {/if}
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

              {#if party}
                <button
                  type="button"
                  class="btn"
                  on:click={clearPartyLobby}
                  disabled={busy}
                >
                  Close Lobby
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
            <a href="#settings-behavior" class="settings-section-link">
              <i class="fas fa-keyboard" aria-hidden="true"></i>
              <span>Behavior</span>
            </a>
            <a href="#settings-editor" class="settings-section-link">
              <i class="fas fa-palette" aria-hidden="true"></i>
              <span>Editor Theme</span>
            </a>
            <a href="#settings-security" class="settings-section-link">
              <i class="fas fa-lock" aria-hidden="true"></i>
              <span>Security</span>
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
                <span>Leaderboard rank</span>
                <strong>
                  {leaderboardCurrentUser
                    ? `#${leaderboardCurrentUser.placement}`
                    : "Unranked"}
                </strong>
              </div>
              <div class="settings-stat-card">
                <span>Live match</span>
                <strong>{match ? match.mode.toUpperCase() : "None"}</strong>
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

        <section id="settings-behavior" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">Behavior</p>
              <h3>Keybind Preferences</h3>
            </div>
            <span class="settings-panel-note">Editor movement and shortcuts</span>
          </div>

          <div class="settings-behavior-list">
            <article class="settings-behavior-row">
              <div class="settings-behavior-copy">
                <div class="settings-behavior-label">
                  <i class="fas fa-star" aria-hidden="true"></i>
                  <span>Keybind profile</span>
                </div>
                <p>
                  Normal keeps the default editor controls. Vim now uses a real
                  CodeMirror Vim package instead of custom in-app motion logic.
                  Custom lets users keep normal typing but tailor action
                  shortcuts.
                </p>
              </div>
              <div
                class="settings-toggle-group"
                role="group"
                aria-label="Keybind profile"
              >
                {#each ["normal", "vim", "custom"] as option}
                  <button
                    type="button"
                    class="settings-toggle-pill"
                    class:active={keybindMode === option}
                    on:click={() => setKeybindMode(option as KeybindMode)}
                  >
                    {option}
                  </button>
                {/each}
              </div>
            </article>

            <article class="settings-behavior-row">
              <div class="settings-behavior-copy">
                <div class="settings-behavior-label">
                  <i class="fas fa-bolt" aria-hidden="true"></i>
                  <span>Action shortcuts</span>
                </div>
                <p>
                  {#if keybindMode === "custom"}
                    Custom mode uses `Alt` plus the letter you choose for each
                    action below.
                  {:else}
                    Built-in shortcuts stay simple: `Ctrl+Enter` submits,
                    `Ctrl+Shift+Enter` runs samples, `Alt+H` asks for a hint,
                    and `Alt+F` forfeits.
                  {/if}
                </p>
              </div>
              <div class="settings-shortcut-summary">
                <span class="settings-shortcut-chip">
                  {keybindMode === "custom" ? customShortcutLabel("submit") : "Ctrl+Enter"}
                  <strong>Submit</strong>
                </span>
                <span class="settings-shortcut-chip">
                  {keybindMode === "custom"
                    ? customShortcutLabel("test")
                    : "Ctrl+Shift+Enter"}
                  <strong>Samples</strong>
                </span>
                <span class="settings-shortcut-chip">
                  {keybindMode === "custom" ? customShortcutLabel("hint") : "Alt+H"}
                  <strong>Hint</strong>
                </span>
                <span class="settings-shortcut-chip">
                  {keybindMode === "custom" ? customShortcutLabel("forfeit") : "Alt+F"}
                  <strong>Forfeit</strong>
                </span>
              </div>
            </article>

            {#if keybindMode === "custom"}
              <article class="settings-shortcut-card">
                <div class="settings-shortcut-card-copy">
                  <div class="settings-behavior-label">
                    <i class="fas fa-sliders" aria-hidden="true"></i>
                    <span>Custom shortcut setup</span>
                  </div>
                  <p>
                    Each action uses `Alt` plus one letter or number. The
                    defaults below are chosen to be easy to remember.
                  </p>
                </div>

                <div class="settings-shortcut-grid">
                  <label class="settings-shortcut-field">
                    <span>Submit</span>
                    <div class="settings-shortcut-input-shell">
                      <span>Alt +</span>
                      <input
                        type="text"
                        maxlength="1"
                        value={customShortcuts.submit.toUpperCase()}
                        on:input={(event) =>
                          setCustomShortcut(
                            "submit",
                            (event.currentTarget as HTMLInputElement).value,
                          )}
                      />
                    </div>
                  </label>
                  <label class="settings-shortcut-field">
                    <span>Run samples</span>
                    <div class="settings-shortcut-input-shell">
                      <span>Alt +</span>
                      <input
                        type="text"
                        maxlength="1"
                        value={customShortcuts.test.toUpperCase()}
                        on:input={(event) =>
                          setCustomShortcut(
                            "test",
                            (event.currentTarget as HTMLInputElement).value,
                          )}
                      />
                    </div>
                  </label>
                  <label class="settings-shortcut-field">
                    <span>Request hint</span>
                    <div class="settings-shortcut-input-shell">
                      <span>Alt +</span>
                      <input
                        type="text"
                        maxlength="1"
                        value={customShortcuts.hint.toUpperCase()}
                        on:input={(event) =>
                          setCustomShortcut(
                            "hint",
                            (event.currentTarget as HTMLInputElement).value,
                          )}
                      />
                    </div>
                  </label>
                  <label class="settings-shortcut-field">
                    <span>Forfeit</span>
                    <div class="settings-shortcut-input-shell">
                      <span>Alt +</span>
                      <input
                        type="text"
                        maxlength="1"
                        value={customShortcuts.forfeit.toUpperCase()}
                        on:input={(event) =>
                          setCustomShortcut(
                            "forfeit",
                            (event.currentTarget as HTMLInputElement).value,
                          )}
                      />
                    </div>
                  </label>
                </div>

                {#if customShortcutError}
                  <p class="flash error">{customShortcutError}</p>
                {/if}
              </article>
            {/if}
          </div>
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

              <div class="settings-control-group">
                <span class="eyebrow">Editor font size</span>
                <div class="segmented">
                  {#each ["compact", "default", "large"] as option}
                    <button
                      type="button"
                      class:active={editorFontSize === option}
                      on:click={() => setEditorFontSize(option as EditorFontSize)}
                    >
                      {option}
                    </button>
                  {/each}
                </div>
                <p class="settings-helper-copy">
                  Font size is usually more useful than a header palette toggle
                  because it improves readability in the live coding view.
                </p>
              </div>
            </article>

            <article class="settings-preview-card">
              <div class="settings-preview-labels">
                <span>{themeStatusText}</span>
                <strong>{activeEditorThemeName} · {editorFontSizeLabel()}</strong>
              </div>
              <div class="settings-code-preview" aria-hidden="true">
                <pre><span class="preview-keyword">def</span> <span class="preview-function">solve</span>(line):
    <span class="preview-keyword">return</span> <span class="preview-string">line</span>.strip()[::<span class="preview-number">-1</span>]  <span class="preview-comment"># hidden-rule ready</span></pre>
              </div>
            </article>
          </div>
        </section>

        <section id="settings-security" class="settings-panel">
          <div class="settings-panel-heading">
            <div>
              <p class="eyebrow">Security</p>
              <h3>Password</h3>
            </div>
            <span class="settings-panel-note">Classic password change flow</span>
          </div>

          {#if !sessionUser || sessionUser.guest}
            <p class="settings-helper-copy">
              Sign in with a registered account to change your password.
            </p>
          {:else}
            <div class="settings-password-grid">
              <label>
                <span>Current password</span>
                <input type="password" bind:value={passwordCurrent} />
              </label>

              <label>
                <span>New password</span>
                <input type="password" bind:value={passwordNext} minlength="6" />
              </label>

              <label>
                <span>Confirm new password</span>
                <input type="password" bind:value={passwordConfirm} minlength="6" />
              </label>
            </div>

            {#if passwordError}
              <p class="flash error">{passwordError}</p>
            {/if}
            {#if passwordNotice}
              <p class="flash notice">{passwordNotice}</p>
            {/if}

            <div class="settings-action-row">
              <button
                type="button"
                class="btn primary"
                on:click={changePassword}
                disabled={passwordBusy ||
                  passwordCurrent.length === 0 ||
                  passwordNext.length < 6 ||
                  passwordConfirm.length < 6}
              >
                {passwordBusy ? "Updating..." : "Update Password"}
              </button>
            </div>
          {/if}
        </section>
      </section>
    </main>
  {:else if activeView === "postmatch"}
    <main id="postmatch-view">
      {#if !postMatch}
        <section class="race-empty">
          <p>No completed match data yet.</p>
          <button type="button" class="btn primary" on:click={showHome}
            >Back Home</button
          >
        </section>
      {:else}
        <section class="postmatch-hero">
          <div>
            <p class="eyebrow">Match complete</p>
            <h1>{postMatch.mode.toUpperCase()} Results</h1>
            <p class="postmatch-subtitle">
              {postMatch.reason} · {postMatch.theme} · {postMatch.difficulty}
            </p>
          </div>
          <div class="postmatch-actions">
            <button type="button" class="btn" on:click={showHome}>Home</button>
            <button type="button" class="btn" on:click={showArena} disabled={!match}
              >View Arena</button
            >
          </div>
        </section>

        <section class="postmatch-stats-grid">
          <article class="postmatch-stat-card">
            <span class="eyebrow">Winner</span>
            <strong>{postMatchWinner(postMatch.standings)?.name ?? "No winner"}</strong>
          </article>
          <article class="postmatch-stat-card">
            <span class="eyebrow">Solved</span>
            <strong>{postMatchSolvedCount(postMatch.standings)}/{postMatch.standings.length}</strong>
          </article>
          <article class="postmatch-stat-card">
            <span class="eyebrow">Forfeits</span>
            <strong>{postMatchForfeitCount(postMatch.standings)}</strong>
          </article>
          <article class="postmatch-stat-card">
            <span class="eyebrow">Time Limit</span>
            <strong>{formatDuration(postMatch.time_limit_seconds)}</strong>
          </article>
        </section>

        <section class="postmatch-board">
          <div class="standings-head">
            <h3>Final board</h3>
          </div>
          <div class="standings-list">
            {#each postMatch.standings as row}
              <article class="standing-row">
                <span class="mono">#{row.placement}</span>
                <span class="name">{row.name}</span>
                <span class="mono">hidden {row.hidden_passed}</span>
                <span class="mono">hint {row.hint_level}</span>
                <span class="mono">ELO {row.elo}</span>
                <span class="mono delta">{formatRatingDelta(row.rating_delta)}</span>
                <span class="state" class:ok={row.solved} class:bad={!row.solved}>
                  {row.forfeited ? "FORFEIT" : row.solved ? "SOLVED" : "OPEN"}
                </span>
              </article>
            {/each}
          </div>
        </section>
      {/if}
      {#if notice}
        <p class="flash notice">{notice}</p>
      {/if}
      {#if error}
        <p class="flash error">{error}</p>
      {/if}
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
                style={`--editor-font-size: ${editorFontSize === "compact"
                  ? "0.82rem"
                  : editorFontSize === "large"
                    ? "1rem"
                    : "0.9rem"}`}
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
                <span class="editor-mode-badge">
                  {keybindMode === "vim"
                    ? "vim package"
                    : keybindMode === "custom"
                      ? "custom shortcuts"
                      : "normal shortcuts"}
                </span>
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
