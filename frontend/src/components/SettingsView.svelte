<script lang="ts">
  import type { BundledTheme } from "shiki/bundle/web";
  import type {
    AppearanceMode,
    EditorAction,
    EditorFontFamily,
    EditorFontSize,
    KeybindMode,
    LeaderboardEntry,
    MatchPayload,
    SessionUser,
    UiTheme,
  } from "../app-types";

  export let sessionUser: SessionUser | null = null;
  export let busy = false;
  export let leaderboardCurrentUser: LeaderboardEntry | null = null;
  export let match: MatchPayload | null = null;
  export let themeStatusText = "";
  export let activeEditorThemeName = "";
  export let profileImageUrl = "";

  export let showPlayView: () => void = () => {};
  export let logout: () => void | Promise<void> = () => {};
  export let refreshSession: () => void | Promise<void> = () => {};
  export let uploadProfileImage: (file: File) => void | Promise<void> = () => {};
  export let userInitial: (name: string | undefined) => string = () => "?";

  export let keybindMode: KeybindMode = "normal";
  export let setKeybindMode: (mode: KeybindMode) => void = () => {};
  export let customShortcuts: Record<EditorAction, string> = {
    submit: "s",
    test: "r",
    hint: "h",
    forfeit: "f",
  };
  export let customShortcutLabel: (action: EditorAction) => string = () => "";
  export let customShortcutError = "";
  export let setCustomShortcut: (action: EditorAction, rawValue: string) => void = () => {};

  export let appearanceMode: AppearanceMode = "light";
  export let appearanceModeOrder: AppearanceMode[] = ["system", "light", "dark"];
  export let setAppearanceMode: (mode: AppearanceMode) => void = () => {};
  export let themePref: UiTheme = "light";
  export let activeEditorTheme: BundledTheme = "everforest-light";
  export let availableEditorThemes: Array<{ id: string; displayName: string }> = [];
  export let setEditorTheme: (themeId: BundledTheme) => void = () => {};
  export let resetThemePreferences: () => void = () => {};
  export let editorFontFamily: EditorFontFamily = "roboto-mono";
  export let editorFontFamilyOptions: Array<{ id: EditorFontFamily; label: string }> = [];
  export let setEditorFontFamily: (family: EditorFontFamily) => void = () => {};
  export let editorFontFamilyLabel: (family?: EditorFontFamily) => string = () => "Roboto Mono";
  export let editorFontSize: EditorFontSize = 14;
  export let editorFontSizeMin = 12;
  export let editorFontSizeMax = 22;
  export let setEditorFontSize: (size: EditorFontSize) => void = () => {};
  export let editorFontSizeLabel: (size?: EditorFontSize) => string = () => "14 px";

  export let passwordCurrent = "";
  export let passwordNext = "";
  export let passwordConfirm = "";
  export let passwordBusy = false;
  export let passwordNotice = "";
  export let passwordError = "";
  export let changePassword: () => void | Promise<void> = () => {};

  let profileImageInputEl: HTMLInputElement | null = null;

  async function handleProfileImageChange(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      await uploadProfileImage(file);
    }
    input.value = "";
  }
</script>

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
          <span>Editor</span>
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
          <h3>User</h3>
        </div>
        <span class="settings-panel-note">
          {sessionUser ? "Connected account" : "Offline preview"}
        </span>
      </div>

      <div class="settings-profile-grid">
        <article class="settings-identity-card">
          <div class="settings-avatar-shell">
            <div class="settings-avatar" aria-hidden={!profileImageUrl}>
              {#if profileImageUrl}
                <img
                  class="avatar-image"
                  src={profileImageUrl}
                  alt={`${sessionUser?.name ?? "User"} profile photo`}
                />
              {:else}
                {userInitial(sessionUser?.name)}
              {/if}
            </div>
            {#if sessionUser}
              <input
                bind:this={profileImageInputEl}
                class="settings-avatar-input"
                type="file"
                accept="image/*"
                on:change={(event) => void handleProfileImageChange(event)}
              />
              <button
                type="button"
                class="settings-avatar-button"
                on:click={() => profileImageInputEl?.click()}
                aria-label="Upload profile photo"
              >
                <i class="fas fa-plus" aria-hidden="true"></i>
              </button>
            {/if}
          </div>
          <div class="settings-identity-copy">
            <strong>{sessionUser?.name ?? "Guest challenger"}</strong>
            <span>
              {sessionUser
                ? `Current ladder rating: ${sessionUser.elo} ELO`
                : "Sign in to persist ranked progress and match history."}
            </span>
            {#if sessionUser}
              <span class="settings-identity-note">Profile photo is stored on this browser.</span>
            {/if}
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
          <h3>Appearance & Typography</h3>
        </div>
        <span class="settings-panel-note">{themePref} mode live preview</span>
      </div>

      <div class="settings-editor-grid">
        <article class="settings-control-card">
          <div class="settings-control-group">
            <span class="eyebrow">Appearance mode</span>
            <div class="segmented">
              {#each appearanceModeOrder as option}
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

          <label>
            <span>Editor font</span>
            <select
              value={editorFontFamily}
              on:change={(event) =>
                setEditorFontFamily(
                  (event.currentTarget as HTMLSelectElement)
                    .value as EditorFontFamily,
                )}
            >
              {#each editorFontFamilyOptions as fontOption}
                <option value={fontOption.id}>{fontOption.label}</option>
              {/each}
            </select>
          </label>

          <div class="settings-control-group">
            <span class="eyebrow">Editor font size</span>
            <div class="settings-font-size-row">
              <input
                type="range"
                min={editorFontSizeMin}
                max={editorFontSizeMax}
                step="1"
                value={editorFontSize}
                on:input={(event) =>
                  setEditorFontSize(
                    Number((event.currentTarget as HTMLInputElement).value),
                  )}
              />
              <label class="settings-font-size-input">
                <span>{editorFontSizeLabel()}</span>
                <input
                  type="number"
                  min={editorFontSizeMin}
                  max={editorFontSizeMax}
                  step="1"
                  value={editorFontSize}
                  on:input={(event) =>
                    setEditorFontSize(
                      Number((event.currentTarget as HTMLInputElement).value),
                    )}
                />
              </label>
            </div>
            <p class="settings-helper-copy">
              Pick the code font and point size that feels best across the
              editor, settings, and match UI.
            </p>
          </div>

          <div class="settings-action-row settings-theme-actions">
            <button
              type="button"
              class="btn"
              on:click={resetThemePreferences}
            >
              Reset to defaults
            </button>
          </div>
        </article>

        <article class="settings-preview-card">
          <div class="settings-preview-labels">
            <span>{themeStatusText}</span>
            <strong>{editorFontFamilyLabel()} | {editorFontSizeLabel()}</strong>
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
