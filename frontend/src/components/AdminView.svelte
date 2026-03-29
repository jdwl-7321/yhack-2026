<script lang="ts">
  import type {
    AdminMatch,
    SessionUser,
  } from "../app-types";

  export let sessionUser: SessionUser | null = null;
  export let isAdmin = false;
  export let busy = false;
  export let adminUsers: SessionUser[] = [];
  export let adminMatches: AdminMatch[] = [];
  export let notice = "";
  export let error = "";

  export let formatDuration: (seconds: number) => string = (seconds) => `${seconds}`;
  export let refreshAdminDashboard: () => void | Promise<void> = () => {};
  export let resetAllElos: () => void | Promise<void> = () => {};
  export let updateUserElo: (
    userId: string,
    elo: number,
  ) => void | Promise<void> = () => {};
  export let deleteUserAccount: (userId: string) => void | Promise<void> = () => {};
  export let cancelActiveMatch: (matchId: string) => void | Promise<void> = () => {};

  let draftEloByUser: Record<string, string> = {};
  let localError = "";

  function eloDraft(user: SessionUser): string {
    return draftEloByUser[user.id] ?? String(user.elo);
  }

  function setEloDraft(userId: string, value: string): void {
    draftEloByUser = { ...draftEloByUser, [userId]: value };
  }

  async function submitUserElo(user: SessionUser): Promise<void> {
    const parsed = Number.parseInt(eloDraft(user), 10);
    if (!Number.isInteger(parsed) || parsed < 0) {
      localError = "ELO must be a non-negative integer.";
      return;
    }
    localError = "";
    await updateUserElo(user.id, parsed);
    setEloDraft(user.id, String(parsed));
  }

  async function confirmDelete(user: SessionUser): Promise<void> {
    const confirmed = window.confirm(
      `Delete account ${user.name}? Active matches for this user will be cancelled.`,
    );
    if (!confirmed) {
      return;
    }
    localError = "";
    await deleteUserAccount(user.id);
  }

  async function confirmCancelMatch(matchId: string): Promise<void> {
    const confirmed = window.confirm(
      `Cancel active match ${matchId}? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    localError = "";
    await cancelActiveMatch(matchId);
  }
</script>

<main id="admin-view">
  {#if !sessionUser}
    <section class="admin-card">
      <h1>Admin Dashboard</h1>
      <p class="admin-muted">Sign in to access admin controls.</p>
    </section>
  {:else if !isAdmin}
    <section class="admin-card">
      <h1>Admin Dashboard</h1>
      <p class="admin-muted">Access denied. This account is not configured as admin.</p>
    </section>
  {:else}
    <section class="admin-hero admin-card">
      <div>
        <p class="eyebrow">Administration</p>
        <h1>Admin Dashboard</h1>
        <p class="admin-muted">Manage accounts, ELO values, and active matches.</p>
      </div>
      <div class="admin-actions">
        <button type="button" class="btn" on:click={() => void refreshAdminDashboard()} disabled={busy}>
          Refresh
        </button>
        <button type="button" class="btn" on:click={() => void resetAllElos()} disabled={busy}>
          Reset all ELO to 1000
        </button>
      </div>
    </section>

    <section class="admin-layout">
      <article class="admin-card">
        <div class="admin-card-head">
          <h2>Players</h2>
          <span>{adminUsers.length} total</span>
        </div>

        <div class="admin-users-grid">
          <div class="admin-users-head">
            <span>Player</span>
            <span>Current ELO</span>
            <span>Update ELO</span>
            <span>Delete</span>
          </div>
          {#each adminUsers as user}
            <div class="admin-users-row">
              <div class="admin-player-cell">
                <strong>{user.name}</strong>
                <small>{user.id}</small>
              </div>
              <span>{user.elo}</span>
              <div class="admin-elo-actions">
                <input
                  type="number"
                  min="0"
                  value={eloDraft(user)}
                  on:input={(event) => {
                    setEloDraft(user.id, (event.currentTarget as HTMLInputElement).value);
                  }}
                  disabled={busy}
                />
                <button
                  type="button"
                  class="btn"
                  on:click={() => void submitUserElo(user)}
                  disabled={busy}
                >
                  Set
                </button>
              </div>
              <button
                type="button"
                class="btn"
                on:click={() => void confirmDelete(user)}
                disabled={busy || user.id === sessionUser.id}
              >
                Delete
              </button>
            </div>
          {/each}
        </div>
      </article>

      <article class="admin-card">
        <div class="admin-card-head">
          <h2>Active Matches</h2>
          <span>{adminMatches.length} live</span>
        </div>

        {#if adminMatches.length === 0}
          <p class="admin-muted">No active matches right now.</p>
        {:else}
          <div class="admin-match-list">
            {#each adminMatches as match}
              <section class="admin-match-row">
                <div class="admin-match-copy">
                  <strong>{match.match_id}</strong>
                  <p>
                    {match.mode.toUpperCase()} · {match.theme} · {match.difficulty.toUpperCase()} ·
                    {formatDuration(match.time_limit_seconds)}
                  </p>
                  <p class="admin-muted">
                    Players: {match.players.map((player) => player.name).join(", ")}
                  </p>
                </div>
                <button
                  type="button"
                  class="btn"
                  on:click={() => void confirmCancelMatch(match.match_id)}
                  disabled={busy}
                >
                  Cancel Match
                </button>
              </section>
            {/each}
          </div>
        {/if}
      </article>
    </section>
  {/if}

  {#if notice}
    <p class="flash notice">{notice}</p>
  {/if}
  {#if error || localError}
    <p class="flash error">{error || localError}</p>
  {/if}
</main>
