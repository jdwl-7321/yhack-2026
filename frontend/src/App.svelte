<script lang="ts">
  import { onMount, tick } from "svelte";
  import { basicSetup, EditorView } from "codemirror";
  import { EditorState } from "@codemirror/state";
  import { indentLess, indentMore } from "@codemirror/commands";
  import { keymap } from "@codemirror/view";
  import {
    HighlightStyle,
    indentUnit,
    syntaxHighlighting,
  } from "@codemirror/language";
  import { python as cmPython } from "@codemirror/lang-python";
  import { tags } from "@lezer/highlight";
  import { getCM, Vim, vim } from "@replit/codemirror-vim";
  import hljs from "highlight.js/lib/core";
  import python from "highlight.js/lib/languages/python";
  import {
    bundledThemes,
    bundledThemesInfo,
    type BundledTheme,
  } from "shiki/bundle/web";
  import AppHeader from "./components/AppHeader.svelte";
  import HomeView from "./components/HomeView.svelte";
  import LeaderboardView from "./components/LeaderboardView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import PostMatchView from "./components/PostMatchView.svelte";
  import ArenaView from "./components/ArenaView.svelte";
  import type {
    AccountOutcome,
    AccountRecentRun,
    AccountStats,
    AppearanceMode,
    AuthMode,
    AuthResponse,
    ConsoleEntry,
    ConsoleType,
    Difficulty,
    EditorAction,
    EditorFontFamily,
    EditorFontSize,
    EditorSnapshot,
    EditorThemePalette,
    JudgePayload,
    KeybindMode,
    LeaderboardEntry,
    LeaderboardPayload,
    LiveStatusTone,
    MatchPayload,
    Mode,
    PartyPayload,
    PostMatchState,
    SampleTest,
    RankedQueuePayload,
    SessionPayload,
    SessionUser,
    ShikiThemeDefinition,
    Standing,
    UiTheme,
    View,
    VimMode,
  } from "./app-types";

  const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
  const FALLBACK_THEME = "Cryptography";
  const INDENT = "    ";
  const LEADERBOARD_LIMIT = 10;
  const PARTY_LIMIT_MIN = 2;
  const PARTY_LIMIT_MAX = 16;
  const PARTY_TIME_EXTENSION_SECONDS = 300;
  const DEFAULT_PARTY_LIMIT = 4;
  const RANKED_QUEUE_POLL_MS = 3000;
  const APPEARANCE_STORAGE_KEY = "yhack.appearance";
  const LIGHT_THEME_STORAGE_KEY = "yhack.editor-theme.light";
  const DARK_THEME_STORAGE_KEY = "yhack.editor-theme.dark";
  const KEYBIND_MODE_STORAGE_KEY = "yhack.keybind-mode";
  const CUSTOM_SHORTCUTS_STORAGE_KEY = "yhack.custom-shortcuts";
  const EDITOR_FONT_FAMILY_STORAGE_KEY = "yhack.editor-font-family";
  const EDITOR_FONT_SIZE_STORAGE_KEY = "yhack.editor-font-size";
  const ACCOUNT_STATS_STORAGE_PREFIX = "yhack.account-stats";
  const ACTIVE_PARTY_STORAGE_PREFIX = "yhack.active-party";
  const DEFAULT_LIGHT_EDITOR_THEME: BundledTheme = "github-light";
  const DEFAULT_DARK_EDITOR_THEME: BundledTheme = "github-dark-default";
  const DEFAULT_EDITOR_FONT_FAMILY: EditorFontFamily = "roboto-mono";
  const DEFAULT_EDITOR_FONT_SIZE = 14;
  const MIN_EDITOR_FONT_SIZE = 12;
  const MAX_EDITOR_FONT_SIZE = 22;
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
  const editorFontFamilyOptions: Array<{
    id: EditorFontFamily;
    label: string;
    cssValue: string;
  }> = [
    {
      id: "roboto-mono",
      label: "Roboto Mono",
      cssValue: "'Roboto Mono', 'Fira Code', 'JetBrains Mono', monospace",
    },
    {
      id: "fira-code",
      label: "Fira Code",
      cssValue: "'Fira Code', 'Roboto Mono', 'JetBrains Mono', monospace",
    },
    {
      id: "jetbrains-mono",
      label: "JetBrains Mono",
      cssValue: "'JetBrains Mono', 'Roboto Mono', 'Fira Code', monospace",
    },
    {
      id: "source-code-pro",
      label: "Source Code Pro",
      cssValue: "'Source Code Pro', 'Roboto Mono', 'Fira Code', monospace",
    },
    {
      id: "ibm-plex-mono",
      label: "IBM Plex Mono",
      cssValue: "'IBM Plex Mono', 'Roboto Mono', 'Fira Code', monospace",
    },
  ];
  const editorFontFamilyById = new Map(
    editorFontFamilyOptions.map((option) => [option.id, option]),
  );
  const vimHighlightStyle = HighlightStyle.define([
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

  if (!hljs.getLanguage("python")) {
    hljs.registerLanguage("python", python);
  }

  const modeOptions: Mode[] = ["zen", "casual", "ranked"];
  const difficultyOptions: Difficulty[] = ["easy", "medium", "hard", "expert"];
  const AUTO_GENERATED_SHARED_SAMPLE_TEMPLATES = new Set<string>([
    "crypto-shift-inference-v2",
    "crypto-substitution-inference-v2",
  ]);

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
  let rankedQueue: RankedQueuePayload | null = null;

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
  let editorFontFamily: EditorFontFamily = DEFAULT_EDITOR_FONT_FAMILY;
  let editorFontSize: EditorFontSize = DEFAULT_EDITOR_FONT_SIZE;
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
  let rankedQueuePollTimer: ReturnType<typeof setTimeout> | null = null;
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

  function activePartyStorageKey(userId: string): string {
    return `${ACTIVE_PARTY_STORAGE_PREFIX}:${userId}`;
  }

  function storedPartyCodeForUser(userId: string): string {
    if (typeof window === "undefined") {
      return "";
    }
    return normalizePartyCode(localStorage.getItem(activePartyStorageKey(userId)) ?? "");
  }

  function rememberPartyCode(partyCode: string): void {
    if (typeof window === "undefined" || !sessionUser) {
      return;
    }
    localStorage.setItem(
      activePartyStorageKey(sessionUser.id),
      normalizePartyCode(partyCode),
    );
  }

  function forgetPartyCode(userId: string | undefined = sessionUser?.id): void {
    if (typeof window === "undefined" || !userId) {
      return;
    }
    localStorage.removeItem(activePartyStorageKey(userId));
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
    match = null;
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
        forgetPartyCode();
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
    if (eventName === "time_extended") {
      setLiveStatus("Host added time to the party", "ok");
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
    const nextSamples =
      eventName === "sample_tests_updated" && nextMatch.sample_tests.length > 0
        ? nextMatch.sample_tests
        : previous.sample_tests;
    match = {
      ...nextMatch,
      scaffold: previous.scaffold,
      sample_tests: nextSamples,
    };
    standings = nextMatch.standings;
    syncSessionElo(nextMatch.standings);

    if (nextMatch.finished) {
      setLiveStatus("Match finished", "ok");
      showPostMatch("Match complete", nextMatch.standings);
      return;
    }

    if (nextMatch.locked) {
      clearTimer();
      timerText = "Paused";
      notice = "Party lobby closed. This match is read-only now.";
      setLiveStatus("Lobby closed by leader", "warn");
      return;
    }

    if (eventName === "submission") {
      setLiveStatus("Standings updated from a submission", "ok");
    }
    if (eventName === "forfeit") {
      setLiveStatus("A player forfeited", "warn");
    }
    if (eventName === "time_extended") {
      startTimer(remainingSecondsForMatch(nextMatch));
      setLiveStatus("Party timer extended", "ok");
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

    if (type === "party.closed") {
      const closedCode = normalizePartyCode(String(payload.code ?? ""));
      if (party && closedCode && party.code === closedCode) {
        party = null;
        joinCodeInput = "";
        notice = "Party lobby was closed by the leader.";
        setLiveStatus("Party closed", "warn");
        forgetPartyCode();
      }
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
  let canAddPartyTime = false;
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
    if (match.locked) {
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

  function stopRankedQueuePolling(): void {
    if (rankedQueuePollTimer) {
      clearTimeout(rankedQueuePollTimer);
      rankedQueuePollTimer = null;
    }
  }

  function syncRankedQueuePolling(): void {
    stopRankedQueuePolling();
    if (
      !sessionUser ||
      activeView !== "home" ||
      rankedQueue?.status !== "queued" ||
      match
    ) {
      return;
    }

    rankedQueuePollTimer = setTimeout(() => {
      rankedQueuePollTimer = null;
      void refreshRankedQueue(true);
    }, RANKED_QUEUE_POLL_MS);
  }

  function clearRankedQueueState(): void {
    rankedQueue = null;
    stopRankedQueuePolling();
  }

  function loadMatchIntoArena(payload: MatchPayload, consoleMessage: string): void {
    clearRankedQueueState();
    match = payload;
    postMatch = null;
    testResult = null;
    submitResult = null;
    hints = payload.free_hint ? [payload.free_hint] : [];
    standings = payload.standings;
    mode = payload.mode;
    difficulty = payload.difficulty;
    selectedTheme = payload.theme;
    timeLimitSeconds = payload.time_limit_seconds;
    syncSessionElo(payload.standings);
    code = payload.scaffold;
    resetEditorHistory(payload.scaffold);

    if (payload.finished) {
      showPostMatch("Match complete", payload.standings);
      return;
    }

    activeView = "arena";
    if (payload.locked) {
      clearTimer();
      timerText = "Paused";
      setLiveStatus("Lobby closed by leader", "warn");
      notice = "Party lobby closed. This match is read-only now.";
    } else {
      startTimer(remainingSecondsForMatch(payload));
    }
    code = payload.scaffold;
    resetConsole();
    if (!payload.locked) {
      setLiveStatus("Match started", "ok");
      appendConsole(`Joined live match: ${payload.theme}`, "system");
    }
    // setLiveStatus("Live match in progress", "ok");
    // appendConsole(consoleMessage, "system");
  }

  async function handleRankedQueuePayload(
    payload: RankedQueuePayload,
    options: {
      fromQueueJoin?: boolean;
      quiet?: boolean;
    } = {},
  ): Promise<void> {
    const fromQueueJoin = options.fromQueueJoin ?? false;
    const quiet = options.quiet ?? false;
    if (payload.status === "idle") {
      clearRankedQueueState();
      if (!quiet) {
        setLiveStatus("Idle", "neutral");
      }
      return;
    }

    mode = "ranked";
    party = null;
    rankedQueue = payload;
    if (payload.status === "matched" && payload.match) {
      clearRankedQueueState();
      loadMatchIntoArena(payload.match, `Ranked match ready: ${payload.match.theme}`);
      updateAccountStats((current) => ({
        ...current,
        matchesStarted: current.matchesStarted + 1,
      }));
      notice = "Opponent found. Ranked match is live.";
      return;
    }

    setLiveStatus("Searching ranked queue", "neutral");
    if (fromQueueJoin) {
      notice = "Joined ranked matchmaking.";
    } else if (!quiet) {
      notice = "Ranked queue refreshed.";
    }
    syncRankedQueuePolling();
  }

  async function openMatchFromLobby(matchId: string): Promise<void> {
    const payload = await api<MatchPayload>(`/api/matches/${matchId}`);
    loadMatchIntoArena(payload, `Joined live match: ${payload.theme}`);
  }

  async function refreshRankedQueue(quiet = false): Promise<void> {
    if (!sessionUser) {
      clearRankedQueueState();
      return;
    }

    try {
      const payload = await api<RankedQueuePayload>("/api/ranked/queue");
      await handleRankedQueuePayload(payload, { quiet });
    } catch (err) {
      clearRankedQueueState();
      if (!quiet) {
        error = toErrorMessage(err);
      }
    }
  }

  async function joinRankedQueue(): Promise<void> {
    if (!sessionUser) {
      error = "Sign in to join ranked matchmaking.";
      activeView = "home";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    party = null;
    try {
      const payload = await api<RankedQueuePayload>("/api/ranked/queue", {
        method: "POST",
        body: JSON.stringify({ user_id: sessionUser.id }),
      });
      await handleRankedQueuePayload(payload, { fromQueueJoin: true });
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function leaveRankedQueue(silent = false): Promise<void> {
    if (!sessionUser) {
      clearRankedQueueState();
      return;
    }

    busy = silent ? busy : true;
    if (!silent) {
      error = "";
      notice = "";
    }
    try {
      await api<RankedQueuePayload>("/api/ranked/queue/leave", {
        method: "POST",
        body: JSON.stringify({ user_id: sessionUser.id }),
      });
      clearRankedQueueState();
      setLiveStatus("Idle", "neutral");
      if (!silent) {
        notice = "Left ranked queue.";
      }
    } catch (err) {
      if (!silent) {
        error = toErrorMessage(err);
      }
    } finally {
      if (!silent) {
        busy = false;
      }
    }
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

  function selectedLineBounds(
    source: string,
    selectionStart: number,
    selectionEnd: number,
  ): { start: number; end: number } {
    const start = source.lastIndexOf("\n", Math.max(0, selectionStart - 1)) + 1;
    const safeEnd = selectionEnd > selectionStart && source[selectionEnd - 1] === "\n"
      ? selectionEnd - 1
      : selectionEnd;
    const nextBreak = source.indexOf("\n", safeEnd);
    const end = nextBreak === -1 ? source.length : nextBreak;
    return { start, end };
  }

  function removableIndentLength(line: string): number {
    const indentMatch = line.match(/^[\t ]+/)?.[0] ?? "";
    if (indentMatch.length === 0) {
      return 0;
    }
    return Math.min(INDENT.length, indentMatch.length);
  }

  function indentSelection(
    target: HTMLTextAreaElement,
    direction: 1 | -1 = 1,
  ): void {
    const { selectionStart, selectionEnd } = target;
    if (selectionStart === selectionEnd) {
      if (direction < 0) {
        const bounds = lineBounds(code, selectionStart);
        const line = code.slice(bounds.start, bounds.end);
        const removable = removableIndentLength(line);
        if (removable === 0) {
          return;
        }
        const nextCode =
          `${code.slice(0, bounds.start)}${line.slice(removable)}${code.slice(bounds.end)}`;
        const cursor = Math.max(bounds.start, selectionStart - removable);
        applyEditorChange(target, nextCode, cursor);
        return;
      }

      const nextCode =
        `${code.slice(0, selectionStart)}${INDENT}${code.slice(selectionEnd)}`;
      const cursor = selectionStart + INDENT.length;
      applyEditorChange(target, nextCode, cursor);
      return;
    }

    const bounds = selectedLineBounds(code, selectionStart, selectionEnd);
    const selection = code.slice(bounds.start, bounds.end);
    const transformed = selection
      .split("\n")
      .map((line) =>
        direction > 0
          ? `${INDENT}${line}`
          : line.slice(removableIndentLength(line)))
      .join("\n");
    const nextCode =
      `${code.slice(0, bounds.start)}${transformed}${code.slice(bounds.end)}`;
    applyEditorChange(
      target,
      nextCode,
      bounds.start,
      bounds.start + transformed.length,
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
      indentSelection(target, event.shiftKey ? -1 : 1);
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
    if (match && !match.locked && !timerInterval) {
      startTimer(remainingSecondsForMatch(match));
    }
    activeView = "arena";
    error = "";
    notice = "";
    setLiveStatus("Live match in progress", "ok");
    accountMenuOpen = false;
  }

  async function resumeRace(): Promise<void> {
    if (!match) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      await openMatchFromLobby(match.match_id);
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
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

  function clampEditorFontSize(value: number): number {
    if (!Number.isFinite(value)) {
      return DEFAULT_EDITOR_FONT_SIZE;
    }
    return Math.min(
      MAX_EDITOR_FONT_SIZE,
      Math.max(MIN_EDITOR_FONT_SIZE, Math.round(value)),
    );
  }

  function editorFontFamilyCssValue(
    family: EditorFontFamily = editorFontFamily,
  ): string {
    return editorFontFamilyById.get(family)?.cssValue ??
      editorFontFamilyById.get(DEFAULT_EDITOR_FONT_FAMILY)?.cssValue ??
      "'Roboto Mono', monospace";
  }

  function applyEditorTypography(): void {
    if (typeof document === "undefined") {
      return;
    }
    const root = document.documentElement;
    const fontFamily = editorFontFamilyCssValue();
    root.style.setProperty("--editor-font-family", fontFamily);
    root.style.setProperty("--font-family", fontFamily);
    root.style.setProperty("--editor-font-size", `${editorFontSize}px`);
  }

  function setEditorFontFamily(family: EditorFontFamily): void {
    if (!editorFontFamilyById.has(family)) {
      return;
    }
    editorFontFamily = family;
    localStorage.setItem(EDITOR_FONT_FAMILY_STORAGE_KEY, family);
    applyEditorTypography();
  }

  function setEditorFontSize(size: EditorFontSize): void {
    editorFontSize = clampEditorFontSize(size);
    localStorage.setItem(
      EDITOR_FONT_SIZE_STORAGE_KEY,
      String(editorFontSize),
    );
    applyEditorTypography();
  }

  function editorFontSizeLabel(size: EditorFontSize = editorFontSize): string {
    return `${clampEditorFontSize(size)} px`;
  }

  function editorFontFamilyLabel(
    family: EditorFontFamily = editorFontFamily,
  ): string {
    return editorFontFamilyById.get(family)?.label ??
      editorFontFamilyById.get(DEFAULT_EDITOR_FONT_FAMILY)?.label ??
      "Roboto Mono";
  }

  function resetThemePreferences(): void {
    appearanceMode = "system";
    lightEditorTheme = DEFAULT_LIGHT_EDITOR_THEME;
    darkEditorTheme = DEFAULT_DARK_EDITOR_THEME;
    editorFontFamily = DEFAULT_EDITOR_FONT_FAMILY;
    editorFontSize = DEFAULT_EDITOR_FONT_SIZE;

    localStorage.setItem(APPEARANCE_STORAGE_KEY, appearanceMode);
    localStorage.setItem(LIGHT_THEME_STORAGE_KEY, lightEditorTheme);
    localStorage.setItem(DARK_THEME_STORAGE_KEY, darkEditorTheme);
    localStorage.setItem(EDITOR_FONT_FAMILY_STORAGE_KEY, editorFontFamily);
    localStorage.setItem(EDITOR_FONT_SIZE_STORAGE_KEY, String(editorFontSize));

    applyEditorTypography();
    syncThemeState();
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
        key: "Tab",
        run: (view) => {
          const cm = getCM(view);
          if (cm?.state.vim?.insertMode) {
            indentMore(view);
            return true;
          }
          if (cm) {
            Vim.handleKey(cm, "<Tab>", "user");
          }
          return true;
        },
      },
      {
        key: "Shift-Tab",
        run: (view) => {
          const cm = getCM(view);
          if (cm?.state.vim?.insertMode) {
            indentLess(view);
            return true;
          }
          if (cm) {
            Vim.handleKey(cm, "<S-Tab>", "user");
          }
          return true;
        },
      },
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
        vim({ status: true }),
        basicSetup,
        EditorState.tabSize.of(INDENT.length),
        indentUnit.of(INDENT),
        cmPython(),
        syntaxHighlighting(vimHighlightStyle),
        createVimActionKeymap(),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            code = update.state.doc.toString();
          }
        }),
      ],
      parent: vimEditorHostEl,
    });

    const cm = getCM(vimEditorView);
    if (cm?.state.vim) {
      const vimCm = cm as typeof cm & {
        state: typeof cm.state & { vim: NonNullable<typeof cm.state.vim> };
      };
      Vim.setOption("pcre", false, vimCm);
    }
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

  function asJsonText(value: unknown): string {
    const rendered = JSON.stringify(value);
    return rendered ?? "null";
  }

  function formatInputDraft(values: unknown[]): string {
    return values
      .map((value, index) => `arg${index + 1} = ${asJsonText(value)}`)
      .join("\n");
  }

  function sampleUsesAutoGeneratedSharedArg(currentMatch: MatchPayload | null): boolean {
    return !!currentMatch && AUTO_GENERATED_SHARED_SAMPLE_TEMPLATES.has(currentMatch.template_key);
  }

  function editableSampleArgCount(currentMatch: MatchPayload | null): number {
    const firstSamplePrimaryArgs = currentMatch?.sample_tests[0]?.primary_inputs;
    if (!Array.isArray(firstSamplePrimaryArgs) || firstSamplePrimaryArgs.length === 0) {
      return 1;
    }
    return firstSamplePrimaryArgs.length;
  }

  function parseSampleInputs(raw: string, maxArgs?: number): unknown[] {
    const validateArity = (values: unknown[]): unknown[] => {
      if (typeof maxArgs === "number" && values.length > maxArgs) {
        throw new Error(
          `arg${maxArgs + 1} is auto-generated from visible samples and cannot be edited.`,
        );
      }
      return values;
    };

    const trimmed = raw.trim();
    if (trimmed.length === 0) {
      throw new Error("Inputs cannot be empty.");
    }

    if (!trimmed.startsWith("arg")) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmed);
      } catch {
        throw new Error("Inputs must be valid JSON.");
      }
      if (!Array.isArray(parsed)) {
        throw new Error("Inputs must be a JSON array of positional arguments.");
      }
      return validateArity(parsed);
    }

    const indexedValues = new Map<number, unknown>();
    for (const line of trimmed.split(/\r?\n/u)) {
      const normalized = line.trim();
      if (!normalized) {
        continue;
      }
      const match = /^arg(\d+)\s*=\s*(.+)$/u.exec(normalized);
      if (!match) {
        throw new Error("Use `arg1 = ...`, `arg2 = ...` input format.");
      }

      const position = Number(match[1]);
      if (!Number.isInteger(position) || position < 1) {
        throw new Error("Argument indexes must start at arg1.");
      }

      let parsedValue: unknown;
      try {
        parsedValue = JSON.parse(match[2]);
      } catch {
        throw new Error(`arg${position} must contain a valid JSON value.`);
      }
      indexedValues.set(position, parsedValue);
    }

    if (indexedValues.size === 0) {
      throw new Error("Inputs cannot be empty.");
    }

    const ordered: unknown[] = [];
    for (let argIndex = 1; argIndex <= indexedValues.size; argIndex += 1) {
      if (!indexedValues.has(argIndex)) {
        throw new Error("Arguments must be contiguous (`arg1`, `arg2`, ...).");
      }
      ordered.push(indexedValues.get(argIndex));
    }
    return validateArity(ordered);
  }

  async function addFirstFailedSampleTest(): Promise<void> {
    if (!match || !sessionUser || !submitResult || submitResult.verdict !== "sample_failed") {
      return;
    }

    const failedSampleIndex = submitResult.sample_passed;
    const failedSample = submitResult.sample_tests[failedSampleIndex];
    if (!failedSample) {
      error = "Failed sample details are unavailable for this submission.";
      return;
    }

    await addSampleTest(formatInputDraft(failedSample.primary_inputs));
  }

  function applyParty(partyPayload: PartyPayload): void {
    party = partyPayload;
    joinCodeInput = partyPayload.join_code;
    mode = partyPayload.mode;
    selectedTheme = partyPayload.settings.theme;
    difficulty = partyPayload.settings.difficulty;
    timeLimitSeconds = partyPayload.settings.time_limit_seconds;
    partyLimit = partyPayload.member_limit;
    rememberPartyCode(partyPayload.code);
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
    const previousUserId = sessionUser?.id;
    const payload = await api<SessionPayload>("/api/auth/session");
    if (!payload.authenticated || !payload.user) {
      forgetPartyCode(previousUserId);
      sessionUser = null;
      accountStats = emptyAccountStats();
      accountMenuOpen = false;
      activeView = "home";
      match = null;
      postMatch = null;
      party = null;
      clearRankedQueueState();
      clearTimer();
      disconnectLiveSocket();
      return;
    }
    sessionUser = payload.user;
    loadAccountStats(payload.user);
    await loadLeaderboard();
    await refreshRankedQueue(true);
    await restorePartyAndMatch(payload.user, storedPartyCodeForUser(payload.user.id));
  }

  async function restorePartyAndMatch(
    user: SessionUser,
    partyCode: string,
  ): Promise<boolean> {
    const normalizedCode = normalizePartyCode(partyCode);
    if (!normalizedCode) {
      return false;
    }

    try {
      const partyPayload = await api<PartyPayload>(
        `/api/parties/${normalizedCode}?t=${Date.now()}`,
      );
      const stillMember = partyPayload.members.some((member) => member.id === user.id);
      if (!stillMember) {
        forgetPartyCode(user.id);
        return false;
      }

      applyParty(partyPayload);
      setLiveStatus("Lobby restored", "ok");

      if (!partyPayload.active_match_id || partyPayload.active_match_finished) {
        if (match && match.party_code === partyPayload.code) {
          match = null;
          standings = [];
        }
        return true;
      }

      const activeMatch = await api<MatchPayload>(
        `/api/matches/${partyPayload.active_match_id}`,
      );
      match = activeMatch;
      postMatch = null;
      testResult = null;
      submitResult = null;
      standings = activeMatch.standings;
      syncSessionElo(activeMatch.standings);
      mode = activeMatch.mode;
      difficulty = activeMatch.difficulty;
      selectedTheme = activeMatch.theme;
      timeLimitSeconds = activeMatch.time_limit_seconds;
      hints = activeMatch.free_hint ? [activeMatch.free_hint] : [];
      code = activeMatch.scaffold;
      resetEditorHistory(activeMatch.scaffold);
      if (activeMatch.locked) {
        clearTimer();
        timerText = "Paused";
        setLiveStatus("Lobby closed by leader", "warn");
        notice = "Party lobby closed. This match is read-only now.";
      } else {
        startTimer(remainingSecondsForMatch(activeMatch));
        setLiveStatus("Active match ready to resume", "ok");
        notice = `You have an active ${activeMatch.mode} match in progress.`;
      }
      return true;
    } catch (err) {
      if (toErrorMessage(err) === "Party not found") {
        forgetPartyCode(user.id);
      }
      return false;
    }
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
      await loadLeaderboard();
      await restorePartyAndMatch(payload.user, storedPartyCodeForUser(payload.user.id));
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
  }

  async function logout(): Promise<void> {
    const previousUserId = sessionUser?.id;
    busy = true;
    error = "";
    notice = "";
    try {
      await api<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
      forgetPartyCode(previousUserId);
      sessionUser = null;
      accountStats = emptyAccountStats();
      accountMenuOpen = false;
      activeView = "home";
      match = null;
      postMatch = null;
      party = null;
      clearRankedQueueState();
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
        forgetPartyCode();
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
      if (payload.active_match_id) {
        setLiveStatus("Match already live. Joining now...", "ok");
        await openMatchFromLobby(payload.active_match_id);
        notice = `Joined party ${payload.join_code}. Entered active match.`;
        return;
      }
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

  async function addPartyTime(): Promise<void> {
    if (
      !party ||
      !sessionUser ||
      party.leader_id !== sessionUser.id ||
      party.mode !== "casual"
    ) {
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<PartyPayload>(`/api/parties/${party.code}/add-time`, {
        method: "POST",
        body: JSON.stringify({
          user_id: sessionUser.id,
          add_seconds: PARTY_TIME_EXTENSION_SECONDS,
        }),
      });
      applyParty(payload);
      setLiveStatus("Added 5 minutes for the party", "ok");
      notice = "Added 5 minutes to the party timer.";
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

  async function clearPartyLobby(): Promise<void> {
    if (!party) {
      return;
    }

    const currentParty = party;
    if (!sessionUser || currentParty.leader_id !== sessionUser.id) {
      party = null;
      joinCodeInput = "";
      forgetPartyCode();
      syncLiveSocket();
      setLiveStatus("Idle", "neutral");
      notice = "Lobby closed.";
      return;
    }

    busy = true;
    error = "";
    notice = "";
    try {
      await api<{ ok: boolean; match_locked: boolean }>(
        `/api/parties/${currentParty.code}/close`,
        {
          method: "POST",
          body: JSON.stringify({ user_id: sessionUser.id }),
        },
      );
      party = null;
      match = null;
      standings = [];
      testResult = null;
      submitResult = null;
      hints = [];
      clearTimer();
      timerText = "00:00";
      joinCodeInput = "";
      forgetPartyCode();
      syncLiveSocket();
      setLiveStatus("Idle", "neutral");
      notice = "Lobby closed.";
    } catch (err) {
      error = toErrorMessage(err);
    } finally {
      busy = false;
    }
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
    let codeToStart = partyCode;

    try {
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
        rememberPartyCode(createdParty.code);
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

      loadMatchIntoArena(payload, `Match loaded: ${payload.theme}`);
      updateAccountStats((current) => ({
        ...current,
        matchesStarted: current.matchesStarted + 1,
      }));

      if (payload.mode === "zen") {
        party = null;
      }

      if (payload.mode !== requestedMode) {
        notice = `Mode switched to ${payload.mode.toUpperCase()} due to ranked eligibility.`;
      }
    } catch (err) {
      const message = toErrorMessage(err);
      if (
        message === "This party already has an active match" &&
        sessionUser &&
        codeToStart
      ) {
        const restored = await restorePartyAndMatch(sessionUser, codeToStart);
        if (restored) {
          error = "";
          notice = "This party already has an active match. Resume when ready.";
          return;
        }
      }

      error = message;
      appendConsole(`System error: ${message}`, "error");
    } finally {
      busy = false;
    }
  }

  async function launchConfiguredMatch(): Promise<void> {
    if (mode === "zen") {
      party = null;
      clearRankedQueueState();
      await startMatch();
      return;
    }

    if (mode === "ranked") {
      party = null;
      await joinRankedQueue();
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
    if (rankedQueue && nextMode !== "ranked") {
      await leaveRankedQueue(true);
    }
    if (party && party.mode !== nextMode) {
      party = null;
      forgetPartyCode();
      setLiveStatus("Idle", "neutral");
    }
    mode = nextMode;
    if (nextMode === "casual") {
      setLiveStatus("Pick create or join to go live", "neutral");
      notice = "Create a party or enter a join code to continue.";
    } else if (nextMode === "ranked") {
      setLiveStatus("Join the ranked queue", "neutral");
      notice = "Queue into a live 1v1 match with a nearby ELO opponent.";
    } else {
      setLiveStatus("Solo mode", "neutral");
      notice = "";
    }
  }

  async function submit(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    if (match.locked) {
      error = "This match has been closed.";
      appendConsole("Submission blocked: match has been closed.", "error");
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
      if (payload.finished) {
        showPostMatch("Match complete", payload.standings);
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
    if (match.locked) {
      error = "This match has been closed.";
      appendConsole("Sample run blocked: match has been closed.", "error");
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
    if (match.locked) {
      error = "This match has been closed.";
      appendConsole("Promotion blocked: match has been closed.", "error");
      return;
    }
    const currentMatchId = match.match_id;
    const currentSubmit = submitResult;

    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await api<{
        sample_tests: SampleTest[];
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

  async function saveSampleTests(
    currentMatchId: string,
    body: Record<string, unknown>,
  ): Promise<void> {
    const payload = await api<{ sample_tests: SampleTest[]; standings: Standing[] }>(
      `/api/matches/${currentMatchId}/sample-tests`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );

    if (match?.match_id === currentMatchId) {
      match = {
        ...match,
        sample_tests: payload.sample_tests,
      };
    }
    standings = payload.standings;
    syncSessionElo(payload.standings);
  }

  async function addSampleTest(inputsText: string): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    const currentMatchId = match.match_id;
    busy = true;
    error = "";

    try {
      const inputs = parseSampleInputs(
        inputsText,
        sampleUsesAutoGeneratedSharedArg(match) ? editableSampleArgCount(match) : undefined,
      );
      await saveSampleTests(currentMatchId, {
        action: "add",
        inputs,
      });
      appendConsole("Added sample test.", "system");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Add sample failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function updateSampleTest(
    index: number,
    inputsText: string,
  ): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    const currentMatchId = match.match_id;
    busy = true;
    error = "";

    try {
      const inputs = parseSampleInputs(
        inputsText,
        sampleUsesAutoGeneratedSharedArg(match) ? editableSampleArgCount(match) : undefined,
      );
      await saveSampleTests(currentMatchId, {
        action: "update",
        index,
        inputs,
      });
      appendConsole(`Updated sample ${index + 1}.`, "system");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Update sample failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function deleteSampleTest(index: number): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    const currentMatchId = match.match_id;
    busy = true;
    error = "";

    try {
      await saveSampleTests(currentMatchId, {
        action: "delete",
        index,
      });
      appendConsole(`Deleted sample ${index + 1}.`, "system");
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Delete sample failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  async function requestHint(): Promise<void> {
    if (!match || !sessionUser) {
      return;
    }
    if (match.locked) {
      error = "This match has been closed.";
      appendConsole("Hint request blocked: match has been closed.", "error");
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
    if (match.locked) {
      error = "This match has been closed.";
      appendConsole("Forfeit blocked: match has been closed.", "error");
      return;
    }
    busy = true;
    error = "";
    try {
      const payload = await api<{ finished: boolean; standings: Standing[] }>(
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
      if (payload.finished) {
        showPostMatch("Match complete", payload.standings);
      }
    } catch (err) {
      error = toErrorMessage(err);
      appendConsole(`Forfeit failed: ${toErrorMessage(err)}`, "error");
    } finally {
      busy = false;
    }
  }

  $: isPartyMode = mode === "casual";
  $: isRankedMode = mode === "ranked";
  $: isPartyLeader = !!party && !!sessionUser && party.leader_id === sessionUser.id;
  $: canEditPartySetup = !party || (isPartyLeader && mode === "casual");
  $: canAddPartyTime =
    !!match &&
    !!party &&
    !!sessionUser &&
    !match.finished &&
    !match.locked &&
    match.mode === "casual" &&
    party.mode === "casual" &&
    party.leader_id === sessionUser.id;
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

  $: {
    sessionUser;
    activeView;
    rankedQueue;
    match;
    syncRankedQueuePolling();
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
  $: if (keybindMode === "vim" && !vimEditorHostEl) {
    destroyVimEditor();
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

    const savedEditorFontFamily = localStorage.getItem(
      EDITOR_FONT_FAMILY_STORAGE_KEY,
    );
    if (
      savedEditorFontFamily === "roboto-mono" ||
      savedEditorFontFamily === "fira-code" ||
      savedEditorFontFamily === "jetbrains-mono" ||
      savedEditorFontFamily === "source-code-pro" ||
      savedEditorFontFamily === "ibm-plex-mono"
    ) {
      editorFontFamily = savedEditorFontFamily;
    }

    const savedEditorFontSize = localStorage.getItem(
      EDITOR_FONT_SIZE_STORAGE_KEY,
    );
    if (savedEditorFontSize) {
      editorFontSize = clampEditorFontSize(Number(savedEditorFontSize));
    }

    applyEditorTypography();

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
      stopRankedQueuePolling();
      destroyVimEditor();
      if (systemMatcher && mediaListener) {
        systemMatcher.removeEventListener("change", mediaListener);
      }
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  });
</script>

<div id="app-shell">
  <AppHeader
    {activeView}
    {appearanceMode}
    {themeStatusText}
    {activeEditorThemeName}
    {themePref}
    {activeEditorTheme}
    {availableEditorThemes}
    {sessionUser}
    {accountStats}
    {accountSolveRate}
    {accountRankLabel}
    {accountPercentileLabel}
    {accountRankedWinLabel}
    {leaderboardTotalPlayers}
    matchSummaryLabel={match ? `${match.mode} · ${timerText}` : "No active match"}
    hasActiveMatch={!!match}
    {busy}
    bind:themeMenuOpen
    bind:accountMenuOpen
    bind:themeMenuEl
    bind:accountMenuEl
    {showHome}
    {showPlayView}
    {toggleLeaderboardView}
    {showSettings}
    {setAppearanceMode}
    {cycleAppearanceMode}
    {toggleThemeMenu}
    {toggleAccountMenu}
    {setEditorTheme}
    {editorFontFamily}
    {editorFontFamilyOptions}
    {editorFontSize}
    {setEditorFontFamily}
    {setEditorFontSize}
    {resetThemePreferences}
    {accountInitials}
    {formatActivityTime}
    {formatRatingDelta}
    {showArena}
    {logout}
  />

  {#if activeView === "home"}
    <HomeView
      {sessionUser}
      {busy}
      bind:authMode
      bind:authName
      bind:authPassword
      bind:mode
      bind:difficulty
      bind:selectedTheme
      bind:timeLimitSeconds
      bind:partyLimit
      bind:joinCodeInput
      {party}
      {rankedQueue}
      {match}
      {timerText}
      {themes}
      {modeOptions}
      {difficultyOptions}
      {isPartyMode}
      {isRankedMode}
      {isPartyLeader}
      {canEditPartySetup}
      {liveStatusText}
      {liveStatusTone}
      {notice}
      {error}
      partyLimitMin={PARTY_LIMIT_MIN}
      partyLimitMax={PARTY_LIMIT_MAX}
      clearFlash={() => {
        error = "";
        notice = "";
      }}
      {startRace}
      {authenticate}
      {updatePartySetup}
      {updatePartyLimit}
      {copyPartyInvite}
      {refreshPartyLobby}
      {joinPartyLobby}
      {kickPartyMember}
      {clearPartyLobby}
      {refreshRankedQueue}
      leaveRankedQueue={() => leaveRankedQueue(false)}
      {launchConfiguredMatch}
      {resumeRace}
      {logout}
      {normalizePartyCode}
    />
  {:else if activeView === "leaderboard"}
    <LeaderboardView
      {leaderboard}
      {sessionUser}
      {leaderboardCurrentUser}
      {leaderboardTotalPlayers}
      {leaderboardPercentile}
      {leaderboardRowNote}
      {loadLeaderboard}
    />
  {:else if activeView === "settings"}
    <SettingsView
      {sessionUser}
      {busy}
      {leaderboardCurrentUser}
      {match}
      {themeStatusText}
      {activeEditorThemeName}
      {showPlayView}
      {logout}
      {refreshSession}
      {userInitial}
      {keybindMode}
      {setKeybindMode}
      {customShortcuts}
      {customShortcutLabel}
      {customShortcutError}
      {setCustomShortcut}
      bind:appearanceMode
      appearanceModeOrder={APPEARANCE_MODE_ORDER}
      {setAppearanceMode}
      {themePref}
      {activeEditorTheme}
      {availableEditorThemes}
      {setEditorTheme}
      {resetThemePreferences}
      {editorFontFamily}
      {editorFontFamilyOptions}
      {setEditorFontFamily}
      {editorFontFamilyLabel}
      {editorFontSize}
      editorFontSizeMin={MIN_EDITOR_FONT_SIZE}
      editorFontSizeMax={MAX_EDITOR_FONT_SIZE}
      {setEditorFontSize}
      {editorFontSizeLabel}
      bind:passwordCurrent
      bind:passwordNext
      bind:passwordConfirm
      {passwordBusy}
      {passwordNotice}
      {passwordError}
      {changePassword}
    />
  {:else if activeView === "postmatch"}
    <PostMatchView
      {postMatch}
      {sessionUser}
      matchId={match?.match_id ?? null}
      {notice}
      {error}
      {showHome}
      {showArena}
      {postMatchWinner}
      {postMatchSolvedCount}
      {postMatchForfeitCount}
      {formatDuration}
      {formatRatingDelta}
    />
  {:else}
    <ArenaView
      {sessionUser}
      {match}
      {busy}
      {timerText}
      {keybindMode}
      {editorFontSize}
      {lineNumbers}
      {editorScrollLeft}
      {highlightedCode}
      bind:code
      {hints}
      {submitResult}
      {testResult}
      {standings}
      {notice}
      {error}
      {consoleEntries}
      bind:lineNumbersEl
      bind:highlightEl
      bind:consoleEl
      bind:vimEditorHostEl
      {launchConfiguredMatch}
      {showHome}
      {raceModeIcon}
      {addSampleTest}
      {updateSampleTest}
      {deleteSampleTest}
      {addFirstFailedSampleTest}
      {promoteFailedTest}
      {requestHint}
      {forfeit}
      {addPartyTime}
      {canAddPartyTime}
      {testSamples}
      {submit}
      {handleEditorInput}
      {handleEditorKeydown}
      {syncEditorScroll}
      {formatRatingDelta}
    />
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
