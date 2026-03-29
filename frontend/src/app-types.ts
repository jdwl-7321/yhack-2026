export type UiTheme = "light" | "dark";
export type AppearanceMode = UiTheme | "system";
export type View = "home" | "arena" | "leaderboard" | "postmatch" | "settings";
export type KeybindMode = "normal" | "vim" | "custom";
export type VimMode = "insert" | "normal";
export type EditorAction = "submit" | "test" | "hint" | "forfeit";
export type EditorFontFamily =
  | "roboto-mono"
  | "fira-code"
  | "jetbrains-mono"
  | "source-code-pro"
  | "ibm-plex-mono";
export type EditorFontSize = number;
export type AuthMode = "register" | "login";
export type Mode = "zen" | "casual" | "ranked";
export type Difficulty = "easy" | "medium" | "hard" | "expert";
export type ConsoleType = "info" | "system" | "success" | "error";

export type SessionUser = {
  id: string;
  name: string;
  guest: boolean;
  elo: number;
};

export type SessionPayload = {
  authenticated: boolean;
  user?: SessionUser;
};

export type AuthResponse = {
  user: SessionUser;
};

export type Standing = {
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

export type LeaderboardEntry = {
  placement: number;
  user_id: string;
  name: string;
  elo: number;
  guest: boolean;
};

export type LeaderboardPayload = {
  leaderboard: LeaderboardEntry[];
  current_user: LeaderboardEntry | null;
  total_players: number;
};

export type MatchPayload = {
  match_id: string;
  party_code: string;
  mode: Mode;
  finished: boolean;
  theme: string;
  difficulty: Difficulty;
  time_limit_seconds: number;
  created_at: number;
  prompt: string;
  free_hint: string;
  scaffold: string;
  sample_tests: Array<{ input: string; output: string }>;
  standings: Standing[];
};

export type PartySettingsPayload = {
  theme: string;
  difficulty: Difficulty;
  time_limit_seconds: number;
  seed: number | null;
};

export type PartyPayload = {
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

export type PostMatchState = {
  reason: string;
  mode: Mode;
  theme: string;
  difficulty: Difficulty;
  time_limit_seconds: number;
  standings: Standing[];
};

export type LiveStatusTone = "neutral" | "ok" | "warn";

export type FailedHiddenTest = {
  input_str: string;
  expected_output: string;
  actual_output: string;
};

export type JudgePayload = {
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

export type ConsoleEntry = {
  id: number;
  text: string;
  type: ConsoleType;
};

export type EditorSnapshot = {
  value: string;
  selectionStart: number;
  selectionEnd: number;
};

export type ShikiThemeDefinition = {
  colors?: Record<string, string>;
  tokenColors?: Array<{
    scope?: string | string[];
    settings?: {
      foreground?: string;
    };
  }>;
};

export type EditorThemePalette = {
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

export type AccountOutcome = "solved" | "forfeit";

export type AccountRecentRun = {
  match_id: string;
  mode: Mode;
  theme: string;
  difficulty: Difficulty;
  outcome: AccountOutcome;
  hidden_passed: number;
  rating_delta: number;
  at: string;
};

export type AccountStats = {
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
