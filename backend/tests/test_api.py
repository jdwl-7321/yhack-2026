from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from app import create_app
from config import ADMIN_USERNAME
from constants import THEMES
from custom_puzzle import DEFAULT_CUSTOM_PUZZLE_SOURCE
from judge import JudgeResult
import store as store_module
from store import MemoryStore, SqliteStore


def _start_single_player_match(
    client: Any,
    *,
    seed: int = 3,
    theme: str | None = None,
    difficulty: str = "easy",
) -> tuple[dict, dict]:
    user = client.post("/api/users", json={"name": "Ada", "guest": False}).get_json()
    assert user is not None

    selected_theme = theme or THEMES[0]

    party = client.post(
        "/api/parties",
        json={
            "leader_id": user["id"],
            "mode": "zen",
            "theme": selected_theme,
            "difficulty": difficulty,
            "time_limit_seconds": 900,
            "seed": seed,
        },
    ).get_json()
    assert party is not None

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": seed, "user_id": user["id"]},
    ).get_json()
    assert match is not None
    return user, match


def _sample_only_solution(sample_tests: list[dict[str, Any]]) -> str:
    if not sample_tests:
        return "def solution() -> int:\n    return 0\n"

    arity = len(sample_tests[0].get("inputs", []))
    params = [f"arg{index + 1}" for index in range(arity)]
    signature = ", ".join(params)

    branch_lines: list[str] = []
    for sample in sample_tests:
        values = sample.get("inputs", [])
        conditions = [
            f"{param} == {value!r}" for param, value in zip(params, values, strict=True)
        ]
        condition = " and ".join(conditions) if conditions else "True"
        branch_lines.extend(
            [
                f"    if {condition}:",
                f"        return {sample['expected']!r}",
            ]
        )

    branch_block = "\n".join(branch_lines)
    fallback = sample_tests[0]["expected"]
    return (
        f"def solution({signature}):\n"
        "    print('trace')\n"
        f"{branch_block}\n"
        f"    return {fallback!r}\n"
    )


def _start_two_player_casual_match(
    client: Any, *, seed: int = 3
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    leader = client.post(
        "/api/users", json={"name": "LeaderOne", "guest": False}
    ).get_json()
    assert leader is not None

    teammate = client.post(
        "/api/users", json={"name": "TeammateTwo", "guest": False}
    ).get_json()
    assert teammate is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "member_limit": 2,
            "seed": seed,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": teammate["id"]},
    )
    assert joined.status_code == 200

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": seed, "user_id": leader["id"]},
    ).get_json()
    assert match is not None
    return leader, teammate, party, match


def _start_two_player_ranked_match(
    client: Any, *, seed: int = 3
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    leader = client.post(
        "/api/users", json={"name": "RankLeader", "guest": False, "elo": 1000}
    ).get_json()
    assert leader is not None

    opponent = client.post(
        "/api/users", json={"name": "RankOpponent", "guest": False, "elo": 1000}
    ).get_json()
    assert opponent is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "member_limit": 2,
            "seed": seed,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": opponent["id"]},
    )
    assert joined.status_code == 200

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": seed, "user_id": leader["id"]},
    ).get_json()
    assert match is not None
    return leader, opponent, party, match


def _register_admin(client: Any) -> dict[str, Any]:
    register = client.post(
        "/api/auth/register",
        json={"name": ADMIN_USERNAME, "password": "secret123"},
    )
    assert register.status_code == 200
    payload = register.get_json()
    assert payload is not None
    return payload["user"]


def _register_user(client: Any, name: str) -> dict[str, Any]:
    response = client.post(
        "/api/auth/register",
        json={"name": name, "password": "secret123"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    return payload["user"]


def _create_custom_puzzle(
    client: Any,
    *,
    title: str,
    source_code: str = DEFAULT_CUSTOM_PUZZLE_SOURCE,
) -> dict[str, Any]:
    response = client.post(
        "/api/puzzles",
        json={"title": title, "source_code": source_code},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    return payload["puzzle"]


def test_auth_session_register_login_logout() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    initial_session = client.get("/api/auth/session").get_json()
    assert initial_session == {"authenticated": False, "is_admin": False}

    register = client.post(
        "/api/auth/register",
        json={"name": "Ada", "password": "secret123"},
    )
    assert register.status_code == 200

    after_register = client.get("/api/auth/session").get_json()
    assert after_register is not None
    assert after_register["authenticated"] is True
    assert after_register["user"]["name"] == "Ada"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/session").get_json() == {
        "authenticated": False,
        "is_admin": False,
    }

    login = client.post(
        "/api/auth/login",
        json={"name": "Ada", "password": "secret123"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/session").get_json()["authenticated"] is True


def test_admin_dashboard_requires_admin_account() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    unauthenticated = client.get("/api/admin/dashboard")
    assert unauthenticated.status_code == 400
    assert unauthenticated.get_json() == {"error": "Authentication required"}

    register = client.post(
        "/api/auth/register",
        json={"name": "RegularUser", "password": "secret123"},
    )
    assert register.status_code == 200

    denied = client.get("/api/admin/dashboard")
    assert denied.status_code == 400
    assert denied.get_json() == {"error": "Admin access required"}


def test_admin_can_reset_and_set_elos_and_cancel_matches() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    _register_admin(client)

    first_user = client.post(
        "/api/users", json={"name": "FirstPlayer", "guest": False, "elo": 1250}
    ).get_json()
    second_user = client.post(
        "/api/users", json={"name": "SecondPlayer", "guest": False, "elo": 900}
    ).get_json()
    assert first_user is not None and second_user is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": first_user["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "member_limit": 2,
            "seed": 101,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": second_user["id"]},
    )
    assert joined.status_code == 200

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": first_user["id"], "seed": 101},
    ).get_json()
    assert match is not None

    dashboard_before = client.get("/api/admin/dashboard")
    assert dashboard_before.status_code == 200
    dashboard_before_payload = dashboard_before.get_json()
    assert dashboard_before_payload is not None
    assert dashboard_before_payload["admin_username"] == ADMIN_USERNAME
    assert any(
        item["match_id"] == match["match_id"]
        for item in dashboard_before_payload["active_matches"]
    )

    reset_response = client.post("/api/admin/elo/reset")
    assert reset_response.status_code == 200
    assert reset_response.get_json() == {"ok": True, "updated_users": 3, "elo": 1000}

    set_elo_response = client.post(
        f"/api/admin/users/{first_user['id']}/elo",
        json={"elo": 1337},
    )
    assert set_elo_response.status_code == 200
    set_elo_payload = set_elo_response.get_json()
    assert set_elo_payload is not None
    assert set_elo_payload["user"]["elo"] == 1337

    cancel_response = client.post(f"/api/admin/matches/{match['match_id']}/cancel")
    assert cancel_response.status_code == 200
    cancelled_match = cancel_response.get_json()
    assert cancelled_match is not None
    assert cancelled_match["match"]["finished"] is True
    assert cancelled_match["match"]["locked"] is True

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["finished"] is True
    assert refreshed_match["locked"] is True


def test_admin_can_delete_users_and_auto_cancel_their_live_matches() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    admin_user = _register_admin(client)

    leader = client.post(
        "/api/users", json={"name": "DeleteLeader", "guest": False, "elo": 1100}
    ).get_json()
    teammate = client.post(
        "/api/users", json={"name": "DeleteMate", "guest": False, "elo": 1110}
    ).get_json()
    assert leader is not None and teammate is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "member_limit": 2,
            "seed": 102,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": teammate["id"]},
    )
    assert joined.status_code == 200

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 102},
    ).get_json()
    assert match is not None

    delete_response = client.delete(f"/api/admin/users/{leader['id']}")
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload is not None
    assert delete_payload["ok"] is True
    assert delete_payload["deleted_user"]["id"] == leader["id"]
    assert delete_payload["cancelled_match_ids"] == [match["match_id"]]

    refreshed_match = client.get(f"/api/matches/{match['match_id']}")
    assert refreshed_match.status_code == 200
    refreshed_payload = refreshed_match.get_json()
    assert refreshed_payload is not None
    assert refreshed_payload["finished"] is True
    assert refreshed_payload["locked"] is True
    standing_ids = {row["user_id"] for row in refreshed_payload["standings"]}
    assert leader["id"] not in standing_ids

    self_delete = client.delete(f"/api/admin/users/{admin_user['id']}")
    assert self_delete.status_code == 400
    assert self_delete.get_json() == {"error": "Admin account cannot delete itself"}


def test_admin_can_update_puzzle_template_source() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    _register_admin(client)

    template_key = "crypto-xor-byte-inference-v1"
    custom_prompt = "Admin-edited XOR prompt for source-of-truth testing."
    custom_hint_1 = "Admin-edited hint level one"

    dashboard = client.get("/api/admin/dashboard").get_json()
    assert dashboard is not None
    assert "missing_puzzle_template_keys" not in dashboard

    source_template = next(
        item
        for item in dashboard["puzzle_templates"]
        if item["template_key"] == template_key
    )
    source_code = source_template["source_code"]
    assert "def case_factory" in source_code

    updated_source = source_code.replace(
        "A deterministic 8-bit XOR mask is used across this match. ",
        f"{custom_prompt} ",
        1,
    ).replace(
        'hint_level_1 = "Every value is an integer byte in the inclusive range 0..255."',
        f'hint_level_1 = "{custom_hint_1}"',
        1,
    )
    assert updated_source != source_code

    try:
        updated = client.post(
            f"/api/admin/puzzles/{template_key}",
            json={"source_code": updated_source},
        )
        assert updated.status_code == 200
        updated_payload = updated.get_json()
        assert updated_payload is not None
        assert custom_prompt in updated_payload["puzzle_template"]["prompt"]
        assert updated_payload["puzzle_template"]["hint_level_1"] == custom_hint_1

        user = client.post(
            "/api/users", json={"name": "PuzzleUser", "guest": False}
        ).get_json()
        assert user is not None

        party = client.post(
            "/api/parties",
            json={
                "leader_id": user["id"],
                "mode": "zen",
                "theme": "Cryptography",
                "difficulty": "easy",
                "time_limit_seconds": 900,
                "seed": 203,
            },
        ).get_json()
        assert party is not None

        match = client.post(
            f"/api/parties/{party['code']}/start",
            json={"seed": 203, "user_id": user["id"]},
        ).get_json()
        assert match is not None
        assert match["template_key"] == template_key
        assert custom_prompt in match["prompt"]
        assert match["free_hint"] == custom_hint_1
    finally:
        restore = client.post(
            f"/api/admin/puzzles/{template_key}",
            json={"source_code": source_code},
        )
        assert restore.status_code == 200


def test_admin_can_create_and_delete_puzzle_templates_from_files() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    _register_admin(client)

    template_key = f"admin-temp-{uuid4().hex[:8]}-v1"

    create_response = client.post(
        "/api/admin/puzzles",
        json={
            "template_key": template_key,
            "theme": "Algorithms",
            "difficulty": "medium",
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    assert create_payload is not None
    assert create_payload["puzzle_template"]["template_key"] == template_key
    source_path = Path(create_payload["puzzle_template"]["source_path"])

    try:
        dashboard = client.get("/api/admin/dashboard").get_json()
        assert dashboard is not None
        assert any(
            template["template_key"] == template_key
            for template in dashboard["puzzle_templates"]
        )

        delete_response = client.delete(f"/api/admin/puzzles/{template_key}")
        assert delete_response.status_code == 200
        assert not source_path.exists()

        dashboard_after_delete = client.get("/api/admin/dashboard").get_json()
        assert dashboard_after_delete is not None
        assert not any(
            template["template_key"] == template_key
            for template in dashboard_after_delete["puzzle_templates"]
        )
    finally:
        if source_path.exists():
            client.delete(f"/api/admin/puzzles/{template_key}")


def test_authenticated_user_can_change_password() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    register = client.post(
        "/api/auth/register",
        json={"name": "Ada", "password": "secret123"},
    )
    assert register.status_code == 200

    change = client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "newsecret456"},
    )
    assert change.status_code == 200
    assert change.get_json() == {"ok": True}

    client.post("/api/auth/logout")

    old_login = client.post(
        "/api/auth/login",
        json={"name": "Ada", "password": "secret123"},
    )
    assert old_login.status_code == 400
    assert old_login.get_json() == {"error": "Invalid credentials"}

    new_login = client.post(
        "/api/auth/login",
        json={"name": "Ada", "password": "newsecret456"},
    )
    assert new_login.status_code == 200


def test_profile_image_is_shared_through_session_and_leaderboard() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    viewer_client = app.test_client()

    owner_register = owner_client.post(
        "/api/auth/register",
        json={"name": "ImageOwner", "password": "secret123"},
    )
    viewer_register = viewer_client.post(
        "/api/auth/register",
        json={"name": "ImageViewer", "password": "secret123"},
    )
    assert owner_register.status_code == 200
    assert viewer_register.status_code == 200

    profile_image_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/"
    updated = owner_client.post(
        "/api/auth/profile-image",
        json={"profile_image_url": profile_image_url},
    )
    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload is not None
    assert updated_payload["user"]["profile_image_url"] == profile_image_url

    owner_session = owner_client.get("/api/auth/session").get_json()
    assert owner_session is not None
    assert owner_session["user"]["profile_image_url"] == profile_image_url

    leaderboard = viewer_client.get("/api/leaderboard?limit=10").get_json()
    assert leaderboard is not None
    owner_entry = next(
        entry for entry in leaderboard["leaderboard"] if entry["name"] == "ImageOwner"
    )
    assert owner_entry["profile_image_url"] == profile_image_url


def test_auth_account_endpoint_updates_preferences_and_stats() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    register = client.post(
        "/api/auth/register",
        json={"name": "AccountStateUser", "password": "secret123"},
    )
    assert register.status_code == 200

    update = client.post(
        "/api/auth/account",
        json={
            "account_preferences": {
                "appearanceMode": "dark",
                "lightEditorTheme": "everforest-light",
                "darkEditorTheme": "catppuccin-mocha",
                "keybindMode": "custom",
                "customShortcuts": {
                    "submit": "q",
                    "test": "w",
                    "hint": "e",
                    "forfeit": "r",
                },
                "editorFontFamily": "jetbrains-mono",
                "editorFontSize": 18,
            },
            "account_stats": {
                "matchesStarted": 4,
                "matchesSolved": 3,
                "rankedFinished": 2,
                "rankedWins": 1,
                "hintsUsed": 5,
                "sampleRuns": 9,
                "submissions": 6,
                "forfeits": 1,
                "bestHiddenPassed": 12,
                "recentRuns": [
                    {
                        "match_id": "m_demo",
                        "mode": "ranked",
                        "theme": THEMES[0],
                        "difficulty": "medium",
                        "outcome": "solved",
                        "hidden_passed": 12,
                        "rating_delta": 18,
                        "at": "2026-03-28T12:34:56.000Z",
                    }
                ],
                "recordedMatchIds": ["m_demo"],
            },
        },
    )
    assert update.status_code == 200
    update_payload = update.get_json()
    assert update_payload is not None
    assert update_payload["user"]["account_preferences"]["appearanceMode"] == "dark"
    assert update_payload["user"]["account_preferences"]["keybindMode"] == "custom"
    assert update_payload["user"]["account_preferences"]["customShortcuts"] == {
        "submit": "q",
        "test": "w",
        "hint": "e",
        "forfeit": "r",
    }
    assert update_payload["user"]["account_preferences"]["editorFontFamily"] == (
        "jetbrains-mono"
    )
    assert update_payload["user"]["account_preferences"]["editorFontSize"] == 18
    assert update_payload["user"]["account_stats"]["sampleRuns"] == 9
    assert update_payload["user"]["account_stats"]["recentRuns"][0]["match_id"] == (
        "m_demo"
    )

    account_read = client.get("/api/auth/account")
    assert account_read.status_code == 200
    read_payload = account_read.get_json()
    assert read_payload is not None
    assert read_payload["user"]["account_preferences"]["appearanceMode"] == "dark"
    assert read_payload["user"]["account_stats"]["sampleRuns"] == 9

    leaderboard = client.get("/api/leaderboard?limit=10")
    assert leaderboard.status_code == 200
    leaderboard_payload = leaderboard.get_json()
    assert leaderboard_payload is not None
    assert leaderboard_payload["current_user"]["account_stats"]["sampleRuns"] == 9


def test_sqlite_auth_persists_between_app_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()
    register = first_client.post(
        "/api/auth/register",
        json={"name": "PersistedUser", "password": "secret123"},
    )
    assert register.status_code == 200

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    login = second_client.post(
        "/api/auth/login",
        json={"name": "PersistedUser", "password": "secret123"},
    )
    assert login.status_code == 200

    session_payload = second_client.get("/api/auth/session").get_json()
    assert session_payload is not None
    assert session_payload["authenticated"] is True
    assert session_payload["user"]["name"] == "PersistedUser"


def test_sqlite_profile_image_persists_between_app_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "profile-image.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()
    register = first_client.post(
        "/api/auth/register",
        json={"name": "AvatarPersist", "password": "secret123"},
    )
    assert register.status_code == 200

    profile_image_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/"
    update_image = first_client.post(
        "/api/auth/profile-image",
        json={"profile_image_url": profile_image_url},
    )
    assert update_image.status_code == 200

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    login = second_client.post(
        "/api/auth/login",
        json={"name": "AvatarPersist", "password": "secret123"},
    )
    assert login.status_code == 200

    session_payload = second_client.get("/api/auth/session").get_json()
    assert session_payload is not None
    assert session_payload["user"]["profile_image_url"] == profile_image_url


def test_sqlite_account_state_persists_between_app_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "account-state.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()
    register = first_client.post(
        "/api/auth/register",
        json={"name": "StatePersist", "password": "secret123"},
    )
    assert register.status_code == 200

    updated = first_client.post(
        "/api/auth/account",
        json={
            "account_preferences": {
                "appearanceMode": "system",
                "lightEditorTheme": "everforest-light",
                "darkEditorTheme": "catppuccin-mocha",
                "keybindMode": "vim",
                "customShortcuts": {
                    "submit": "s",
                    "test": "r",
                    "hint": "h",
                    "forfeit": "f",
                },
                "editorFontFamily": "ibm-plex-mono",
                "editorFontSize": 16,
            },
            "account_stats": {
                "matchesStarted": 7,
                "matchesSolved": 5,
                "rankedFinished": 4,
                "rankedWins": 3,
                "hintsUsed": 8,
                "sampleRuns": 11,
                "submissions": 9,
                "forfeits": 2,
                "bestHiddenPassed": 14,
                "recentRuns": [],
                "recordedMatchIds": ["m_one", "m_two"],
            },
        },
    )
    assert updated.status_code == 200

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    login = second_client.post(
        "/api/auth/login",
        json={"name": "StatePersist", "password": "secret123"},
    )
    assert login.status_code == 200

    account_payload = second_client.get("/api/auth/account").get_json()
    assert account_payload is not None
    assert account_payload["user"]["account_preferences"]["appearanceMode"] == "system"
    assert account_payload["user"]["account_preferences"]["keybindMode"] == "vim"
    assert account_payload["user"]["account_preferences"]["editorFontFamily"] == (
        "ibm-plex-mono"
    )
    assert account_payload["user"]["account_preferences"]["editorFontSize"] == 16
    assert account_payload["user"]["account_stats"]["matchesStarted"] == 7
    assert account_payload["user"]["account_stats"]["sampleRuns"] == 11
    assert account_payload["user"]["account_stats"]["recordedMatchIds"] == [
        "m_one",
        "m_two",
    ]


def test_sqlite_changed_password_persists_between_app_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "auth-password.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()
    register = first_client.post(
        "/api/auth/register",
        json={"name": "ResetUser", "password": "secret123"},
    )
    assert register.status_code == 200

    changed = first_client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "reset456"},
    )
    assert changed.status_code == 200

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    failed_old = second_client.post(
        "/api/auth/login",
        json={"name": "ResetUser", "password": "secret123"},
    )
    assert failed_old.status_code == 400

    login = second_client.post(
        "/api/auth/login",
        json={"name": "ResetUser", "password": "reset456"},
    )
    assert login.status_code == 200


def test_custom_puzzle_owner_payload_and_non_owner_preview() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    viewer_client = app.test_client()

    _register_user(owner_client, "PuzzleOwner")
    _register_user(viewer_client, "PuzzleViewer")

    created = _create_custom_puzzle(owner_client, title="Offset Practice")
    assert created["can_edit"] is True
    assert created["source_code"]
    assert created["share_path"] == f"/puzzles/{created['slug']}"

    mine = owner_client.get("/api/puzzles/mine")
    assert mine.status_code == 200
    mine_payload = mine.get_json()
    assert mine_payload is not None
    assert mine_payload["puzzles"][0]["slug"] == created["slug"]

    owner_view = owner_client.get(f"/api/puzzles/{created['slug']}")
    assert owner_view.status_code == 200
    owner_payload = owner_view.get_json()
    assert owner_payload is not None
    assert owner_payload["puzzle"]["can_edit"] is True
    assert "source_code" in owner_payload["puzzle"]

    viewer_view = viewer_client.get(f"/api/puzzles/{created['slug']}")
    assert viewer_view.status_code == 200
    viewer_payload = viewer_view.get_json()
    assert viewer_payload is not None
    assert viewer_payload["puzzle"]["can_edit"] is False
    assert "source_code" not in viewer_payload["puzzle"]

    updated = owner_client.post(
        f"/api/puzzles/{created['slug']}",
        json={
            "title": "Offset Practice Revised",
            "source_code": DEFAULT_CUSTOM_PUZZLE_SOURCE.replace(
                "return value + offset",
                "return value - offset",
                2,
            ).replace("output=value + offset", "output=value - offset", 1),
        },
    )
    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload is not None
    assert updated_payload["puzzle"]["title"] == "Offset Practice Revised"


def test_custom_collection_owner_payload_and_non_owner_preview() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    viewer_client = app.test_client()

    _register_user(owner_client, "CollectionOwner")
    _register_user(viewer_client, "CollectionViewer")
    first = _create_custom_puzzle(owner_client, title="First Puzzle")
    second = _create_custom_puzzle(owner_client, title="Second Puzzle")

    created = owner_client.post(
        "/api/collections",
        json={
            "title": "Warmup Set",
            "puzzle_ids": [first["id"], second["id"]],
        },
    )
    assert created.status_code == 200
    created_payload = created.get_json()
    assert created_payload is not None
    collection = created_payload["collection"]
    assert collection["can_edit"] is True
    assert collection["puzzle_ids"] == [first["id"], second["id"]]

    viewer_view = viewer_client.get(f"/api/collections/{collection['slug']}")
    assert viewer_view.status_code == 200
    viewer_payload = viewer_view.get_json()
    assert viewer_payload is not None
    assert viewer_payload["collection"]["can_edit"] is False
    assert "puzzle_ids" not in viewer_payload["collection"]
    assert "puzzles" not in viewer_payload["collection"]


def test_shared_custom_puzzle_can_start_zen_and_casual_matches() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    player_client = app.test_client()
    teammate_client = app.test_client()

    owner = _register_user(owner_client, "SourceOwner")
    player = _register_user(player_client, "ZenPlayer")
    teammate = _register_user(teammate_client, "CasualMate")
    puzzle = _create_custom_puzzle(owner_client, title="Shared Offset")

    zen_party = player_client.post(
        "/api/parties",
        json={
            "mode": "zen",
            "time_limit_seconds": 900,
            "puzzle_selection": {"kind": "shared_puzzle", "slug": puzzle["slug"]},
        },
    )
    assert zen_party.status_code == 200
    zen_party_payload = zen_party.get_json()
    assert zen_party_payload is not None
    assert zen_party_payload["puzzle_source"]["kind"] == "shared_puzzle"

    zen_match = player_client.post(
        f"/api/parties/{zen_party_payload['code']}/start",
        json={
            "user_id": player["id"],
            "time_limit_seconds": 900,
            "puzzle_selection": {"kind": "shared_puzzle", "slug": puzzle["slug"]},
            "seed": 11,
        },
    )
    assert zen_match.status_code == 200
    zen_match_payload = zen_match.get_json()
    assert zen_match_payload is not None
    assert zen_match_payload["puzzle_source"]["kind"] == "shared_puzzle"
    assert zen_match_payload["puzzle_source"]["slug"] == puzzle["slug"]

    casual_party = player_client.post(
        "/api/parties",
        json={
            "mode": "casual",
            "member_limit": 2,
            "time_limit_seconds": 900,
            "puzzle_selection": {"kind": "shared_puzzle", "slug": puzzle["slug"]},
        },
    )
    assert casual_party.status_code == 200
    casual_party_payload = casual_party.get_json()
    assert casual_party_payload is not None

    joined = player_client.post(
        f"/api/parties/{casual_party_payload['code']}/join",
        json={"user_id": teammate["id"]},
    )
    assert joined.status_code == 200

    casual_match = player_client.post(
        f"/api/parties/{casual_party_payload['code']}/start",
        json={
            "user_id": player["id"],
            "time_limit_seconds": 900,
            "puzzle_selection": {"kind": "shared_puzzle", "slug": puzzle["slug"]},
            "seed": 12,
        },
    )
    assert casual_match.status_code == 200
    casual_match_payload = casual_match.get_json()
    assert casual_match_payload is not None
    assert casual_match_payload["puzzle_source"]["kind"] == "shared_puzzle"
    assert casual_match_payload["standings"][0]["user_id"] in {player["id"], teammate["id"]}


def test_shared_collection_fixed_run_and_selection_reset() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    player_client = app.test_client()

    _register_user(owner_client, "FixedOwner")
    player = _register_user(player_client, "FixedRunner")
    first = _create_custom_puzzle(owner_client, title="Alpha")
    second = _create_custom_puzzle(owner_client, title="Beta")
    collection_response = owner_client.post(
        "/api/collections",
        json={"title": "Fixed Set", "puzzle_ids": [first["id"], second["id"]]},
    )
    assert collection_response.status_code == 200
    collection = collection_response.get_json()["collection"]

    party_response = player_client.post(
        "/api/parties",
        json={
            "mode": "zen",
            "time_limit_seconds": 900,
            "puzzle_selection": {
                "kind": "shared_collection",
                "slug": collection["slug"],
                "run_mode": "fixed",
            },
        },
    )
    assert party_response.status_code == 200
    party = party_response.get_json()
    assert party is not None

    first_match = player_client.post(
        f"/api/parties/{party['code']}/start",
        json={
            "user_id": player["id"],
            "time_limit_seconds": 900,
            "puzzle_selection": {
                "kind": "shared_collection",
                "slug": collection["slug"],
                "run_mode": "fixed",
            },
            "seed": 21,
        },
    )
    assert first_match.status_code == 200
    first_payload = first_match.get_json()
    assert first_payload is not None
    assert first_payload["puzzle_source"]["kind"] == "shared_collection"
    assert first_payload["puzzle_source"]["current_puzzle_slug"] == first["slug"]

    finished = player_client.post(f"/api/matches/{first_payload['match_id']}/finish")
    assert finished.status_code == 200

    second_match = player_client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": player["id"], "seed": 22},
    )
    assert second_match.status_code == 200
    second_payload = second_match.get_json()
    assert second_payload is not None
    assert second_payload["puzzle_source"]["current_puzzle_slug"] == second["slug"]
    assert (
        player_client.post(f"/api/matches/{second_payload['match_id']}/finish").status_code
        == 200
    )

    reset_to_catalog = player_client.post(
        f"/api/parties/{party['code']}/settings",
        json={
            "user_id": player["id"],
            "time_limit_seconds": 900,
            "puzzle_selection": {
                "kind": "catalog",
                "theme": THEMES[0],
                "difficulty": "easy",
            },
        },
    )
    assert reset_to_catalog.status_code == 200

    reset_back = player_client.post(
        f"/api/parties/{party['code']}/settings",
        json={
            "user_id": player["id"],
            "time_limit_seconds": 900,
            "puzzle_selection": {
                "kind": "shared_collection",
                "slug": collection["slug"],
                "run_mode": "fixed",
            },
        },
    )
    assert reset_back.status_code == 200

    restarted = player_client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": player["id"], "seed": 23},
    )
    assert restarted.status_code == 200
    restarted_payload = restarted.get_json()
    assert restarted_payload is not None
    assert restarted_payload["puzzle_source"]["current_puzzle_slug"] == first["slug"]


def test_shared_collection_random_skip_and_non_leader_rejection() -> None:
    app = create_app(MemoryStore())
    owner_client = app.test_client()
    leader_client = app.test_client()
    teammate_client = app.test_client()

    _register_user(owner_client, "RandomOwner")
    leader = _register_user(leader_client, "RandomLeader")
    teammate = _register_user(teammate_client, "RandomMate")
    first = _create_custom_puzzle(owner_client, title="Gamma")
    second = _create_custom_puzzle(owner_client, title="Delta")
    collection_response = owner_client.post(
        "/api/collections",
        json={"title": "Random Set", "puzzle_ids": [first["id"], second["id"]]},
    )
    assert collection_response.status_code == 200
    collection = collection_response.get_json()["collection"]

    party_response = leader_client.post(
        "/api/parties",
        json={
            "mode": "casual",
            "member_limit": 2,
            "time_limit_seconds": 900,
            "puzzle_selection": {
                "kind": "shared_collection",
                "slug": collection["slug"],
                "run_mode": "random",
            },
        },
    )
    assert party_response.status_code == 200
    party = party_response.get_json()
    assert party is not None

    joined = leader_client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": teammate["id"]},
    )
    assert joined.status_code == 200

    first_match = leader_client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 31},
    )
    assert first_match.status_code == 200
    first_payload = first_match.get_json()
    assert first_payload is not None
    first_slug = first_payload["puzzle_source"]["current_puzzle_slug"]
    assert first_slug in {first["slug"], second["slug"]}

    denied_skip = leader_client.post(
        f"/api/matches/{first_payload['match_id']}/skip-collection-puzzle",
        json={"user_id": teammate["id"], "seed": 32},
    )
    assert denied_skip.status_code == 400
    assert denied_skip.get_json() == {"error": "Only the party leader can do that"}

    skipped = leader_client.post(
        f"/api/matches/{first_payload['match_id']}/skip-collection-puzzle",
        json={"user_id": leader["id"], "seed": 33},
    )
    assert skipped.status_code == 200
    skipped_payload = skipped.get_json()
    assert skipped_payload is not None
    second_slug = skipped_payload["match"]["puzzle_source"]["current_puzzle_slug"]
    assert second_slug in {first["slug"], second["slug"]}
    assert second_slug != first_slug

    no_remaining = leader_client.post(
        f"/api/matches/{skipped_payload['match']['match_id']}/skip-collection-puzzle",
        json={"user_id": leader["id"], "seed": 34},
    )
    assert no_remaining.status_code == 400
    assert no_remaining.get_json() == {
        "error": "No remaining puzzle exists in this collection run"
    }


def test_custom_puzzle_validation_rejects_unsafe_source() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    _register_user(client, "UnsafeAuthor")

    response = client.post(
        "/api/puzzles",
        json={
            "title": "Unsafe Puzzle",
            "source_code": "import os\nprompt = 'x'\ncontract = FunctionContract(parameter_types=('int',), return_type='int')\n"
            "def variable_factory(rng, _difficulty):\n    return {}\n"
            "def case_factory(rng, _difficulty, params):\n    return TestCase(inputs=(1,), output=1)\n"
            "def shared_input_factory(_params, _sample_tests):\n    return ()\n"
            "def expected_output_for_primary_inputs(*, variables, primary_inputs):\n    return 1\n",
        },
    )
    assert response.status_code == 400
    assert "Imports are not allowed" in response.get_json()["error"]


def test_sqlite_custom_puzzles_and_collections_persist_between_app_instances(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "custom-content.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()
    _register_user(first_client, "PersistAuthor")
    puzzle = _create_custom_puzzle(first_client, title="Persisted Custom")
    collection_response = first_client.post(
        "/api/collections",
        json={"title": "Persisted Set", "puzzle_ids": [puzzle["id"]]},
    )
    assert collection_response.status_code == 200
    collection = collection_response.get_json()["collection"]

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    login = second_client.post(
        "/api/auth/login",
        json={"name": "PersistAuthor", "password": "secret123"},
    )
    assert login.status_code == 200

    mine_puzzles = second_client.get("/api/puzzles/mine")
    assert mine_puzzles.status_code == 200
    assert mine_puzzles.get_json()["puzzles"][0]["slug"] == puzzle["slug"]

    mine_collections = second_client.get("/api/collections/mine")
    assert mine_collections.status_code == 200
    assert mine_collections.get_json()["collections"][0]["slug"] == collection["slug"]


def test_create_party_uses_authenticated_session_user() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    user = client.post(
        "/api/auth/register",
        json={"name": "Leader", "password": "secret123"},
    ).get_json()
    assert user is not None

    party = client.post(
        "/api/parties",
        json={
            "mode": "zen",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "seed": 3,
        },
    ).get_json()

    assert party is not None
    assert party["leader_id"] == user["user"]["id"]


def test_leaderboard_returns_top_players_and_current_user_rank() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    register = client.post(
        "/api/auth/register",
        json={"name": "MidPlayer", "password": "secret123"},
    )
    assert register.status_code == 200

    client.post("/api/users", json={"name": "Ace", "guest": False, "elo": 1480})
    client.post("/api/users", json={"name": "Blair", "guest": False, "elo": 1325})
    client.post("/api/users", json={"name": "Casey", "guest": False, "elo": 1180})

    response = client.get("/api/leaderboard?limit=2")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload is not None
    assert payload["total_players"] == 4
    assert [entry["name"] for entry in payload["leaderboard"]] == ["Ace", "Blair"]
    assert [entry["placement"] for entry in payload["leaderboard"]] == [1, 2]
    assert payload["current_user"]["name"] == "MidPlayer"
    assert payload["current_user"]["placement"] == 4
    assert payload["current_user"]["elo"] == 1000


def test_ranked_party_falls_back_to_casual_with_guest() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    guest = client.post(
        "/api/users",
        json={"name": "Guest", "guest": True, "elo": 1000},
    ).get_json()

    assert leader is not None and guest is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "seed": 7,
        },
    ).get_json()
    assert party is not None

    client.post(f"/api/parties/{party['code']}/join", json={"user_id": guest["id"]})

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": 7, "user_id": leader["id"]},
    ).get_json()
    assert match is not None
    assert match["mode"] == "casual"


def test_ranked_queue_matches_registered_players_by_elo() -> None:
    app = create_app(MemoryStore())
    first_client = app.test_client()
    second_client = app.test_client()

    first_register = first_client.post(
        "/api/auth/register",
        json={"name": "RankedOne", "password": "secret123"},
    )
    second_register = second_client.post(
        "/api/auth/register",
        json={"name": "RankedTwo", "password": "secret123"},
    )
    assert first_register.status_code == 200
    assert second_register.status_code == 200

    store = cast(MemoryStore, app.config["store"])
    first_user = first_register.get_json()["user"]
    second_user = second_register.get_json()["user"]
    store.users[first_user["id"]].elo = 1040
    store.users[second_user["id"]].elo = 1095

    queued = first_client.post("/api/ranked/queue", json={"seed": 13})
    assert queued.status_code == 200
    queued_payload = queued.get_json()
    assert queued_payload is not None
    assert queued_payload["status"] == "queued"
    assert queued_payload["queued_players"] == 1
    assert queued_payload["match"] is None

    matched = second_client.post("/api/ranked/queue", json={"seed": 13})
    assert matched.status_code == 200
    matched_payload = matched.get_json()
    assert matched_payload is not None
    assert matched_payload["status"] == "matched"
    assert matched_payload["match"]["mode"] == "ranked"
    assert matched_payload["match"]["difficulty"] == "medium"

    first_status = first_client.get("/api/ranked/queue")
    assert first_status.status_code == 200
    first_payload = first_status.get_json()
    assert first_payload is not None
    assert first_payload["status"] == "matched"
    assert first_payload["match"]["match_id"] == matched_payload["match"]["match_id"]
    assert {row["name"] for row in first_payload["match"]["standings"]} == {
        "RankedOne",
        "RankedTwo",
    }


def test_ranked_queue_rejects_guest_accounts() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    guest = client.post("/api/users", json={"name": "Guesty", "guest": True}).get_json()
    assert guest is not None

    with client.session_transaction() as session_data:
        session_data["user_id"] = guest["id"]

    response = client.post("/api/ranked/queue")
    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Ranked matchmaking requires a registered account"
    }


def test_ranked_queue_leave_clears_entry() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    register = client.post(
        "/api/auth/register",
        json={"name": "QueueExit", "password": "secret123"},
    )
    assert register.status_code == 200

    join = client.post("/api/ranked/queue")
    assert join.status_code == 200
    assert join.get_json()["status"] == "queued"

    leave = client.post("/api/ranked/queue/leave")
    assert leave.status_code == 200
    assert leave.get_json()["status"] == "idle"

    status = client.get("/api/ranked/queue")
    assert status.status_code == 200
    assert status.get_json()["status"] == "idle"


def test_casual_party_join_code_and_member_limit_are_enforced() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()
    extra = client.post(
        "/api/users",
        json={"name": "Extra", "guest": False, "elo": 1160},
    ).get_json()

    assert leader is not None and member is not None and extra is not None

    party_response = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "medium",
            "time_limit_seconds": 600,
            "member_limit": 2,
            "seed": 31,
        },
    )
    assert party_response.status_code == 200
    party = party_response.get_json()
    assert party is not None
    assert party["join_code"] == party["code"]
    assert party["member_limit"] == 2

    join_ok = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": member["id"]},
    )
    assert join_ok.status_code == 200
    assert join_ok.get_json()["is_full"] is True

    join_full = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": extra["id"]},
    )
    assert join_full.status_code == 400
    assert join_full.get_json() == {"error": "Party is full"}


def test_party_leader_can_set_limit_and_kick_members() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()

    assert leader is not None and member is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "hard",
            "time_limit_seconds": 3600,
            "member_limit": 4,
            "seed": 41,
        },
    ).get_json()
    assert party is not None

    client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": member["id"]},
    )

    reduced_limit = client.post(
        f"/api/parties/{party['code']}/limit",
        json={"user_id": leader["id"], "member_limit": 3},
    )
    assert reduced_limit.status_code == 200
    assert reduced_limit.get_json()["member_limit"] == 3

    denied_kick = client.post(
        f"/api/parties/{party['code']}/kick",
        json={"user_id": member["id"], "member_id": leader["id"]},
    )
    assert denied_kick.status_code == 400
    assert denied_kick.get_json() == {"error": "Only the party leader can do that"}

    kick = client.post(
        f"/api/parties/{party['code']}/kick",
        json={"user_id": leader["id"], "member_id": member["id"]},
    )
    assert kick.status_code == 200
    kicked_party = kick.get_json()
    assert kicked_party is not None
    assert [entry["id"] for entry in kicked_party["members"]] == [leader["id"]]


def test_party_leader_can_update_party_settings() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()

    assert leader is not None and member is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "member_limit": 4,
            "seed": 41,
        },
    ).get_json()
    assert party is not None

    denied = client.post(
        f"/api/parties/{party['code']}/settings",
        json={
            "user_id": member["id"],
            "theme": THEMES[1],
            "difficulty": "hard",
            "time_limit_seconds": 900,
        },
    )
    assert denied.status_code == 400
    assert denied.get_json() == {"error": "Only the party leader can do that"}

    updated = client.post(
        f"/api/parties/{party['code']}/settings",
        json={
            "user_id": leader["id"],
            "theme": THEMES[1],
            "difficulty": "hard",
            "time_limit_seconds": 900,
            "seed": 222,
        },
    )
    assert updated.status_code == 200
    payload = updated.get_json()
    assert payload is not None
    assert payload["settings"]["theme"] == THEMES[1]
    assert payload["settings"]["difficulty"] == "hard"
    assert payload["settings"]["time_limit_seconds"] == 900
    assert payload["settings"]["seed"] == 222


def test_create_party_defaults_to_basic_match_setup() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "PartyLeader", "guest": False, "elo": 1200},
    ).get_json()
    assert leader is not None

    created = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "member_limit": 4,
        },
    )
    assert created.status_code == 200

    payload = created.get_json()
    assert payload is not None
    assert payload["settings"]["theme"] == THEMES[0]
    assert payload["settings"]["difficulty"] == "easy"
    assert payload["settings"]["time_limit_seconds"] == 900


def test_party_match_start_uses_per_match_settings_payload() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()
    assert leader is not None and member is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "member_limit": 4,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": member["id"]},
    )
    assert joined.status_code == 200

    selected_theme = THEMES[1] if len(THEMES) > 1 else THEMES[0]
    started = client.post(
        f"/api/parties/{party['code']}/start",
        json={
            "user_id": leader["id"],
            "theme": selected_theme,
            "difficulty": "easy",
            "time_limit_seconds": 1200,
            "seed": 77,
        },
    )
    assert started.status_code == 200

    match_payload = started.get_json()
    assert match_payload is not None
    assert match_payload["theme"] == selected_theme
    assert match_payload["difficulty"] == "easy"
    assert match_payload["time_limit_seconds"] == 1200

    refreshed_party = client.get(f"/api/parties/{party['code']}").get_json()
    assert refreshed_party is not None
    assert refreshed_party["settings"]["theme"] == selected_theme
    assert refreshed_party["settings"]["difficulty"] == "easy"
    assert refreshed_party["settings"]["time_limit_seconds"] == 1200


def test_party_leader_can_add_time_to_casual_lobby_and_active_match() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader, teammate, party, match = _start_two_player_casual_match(client, seed=77)

    denied = client.post(
        f"/api/parties/{party['code']}/add-time",
        json={"user_id": teammate["id"], "add_seconds": 120},
    )
    assert denied.status_code == 400
    assert denied.get_json() == {"error": "Only the party leader can do that"}

    extended = client.post(
        f"/api/parties/{party['code']}/add-time",
        json={"user_id": leader["id"], "add_seconds": 120},
    )
    assert extended.status_code == 200
    extended_payload = extended.get_json()
    assert extended_payload is not None
    assert extended_payload["settings"]["time_limit_seconds"] == 1020

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["time_limit_seconds"] == 1020


def test_add_time_rejects_ranked_party_mode() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "RankedLeader", "guest": False, "elo": 1200},
    ).get_json()
    assert leader is not None

    ranked_party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "member_limit": 2,
        },
    ).get_json()
    assert ranked_party is not None

    invalid = client.post(
        f"/api/parties/{ranked_party['code']}/add-time",
        json={"user_id": leader["id"], "add_seconds": 120},
    )
    assert invalid.status_code == 400
    assert invalid.get_json() == {
        "error": "Time can only be added in casual or zen parties"
    }


def test_party_leader_can_add_time_to_zen_active_match() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    user, match = _start_single_player_match(client, seed=78)

    extended = client.post(
        f"/api/parties/{match['party_code']}/add-time",
        json={"user_id": user["id"], "add_seconds": 120},
    )
    assert extended.status_code == 200
    extended_payload = extended.get_json()
    assert extended_payload is not None
    assert extended_payload["settings"]["time_limit_seconds"] == 1020

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["time_limit_seconds"] == 1020


def test_only_party_leader_can_start_match() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()

    assert leader is not None and member is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "member_limit": 3,
            "seed": 45,
        },
    ).get_json()
    assert party is not None

    client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": member["id"]},
    )

    denied = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": member["id"], "seed": 45},
    )
    assert denied.status_code == 400
    assert denied.get_json() == {"error": "Only the party leader can start the match"}

    started = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 45},
    )
    assert started.status_code == 200


def test_party_reports_active_match_and_blocks_second_live_start() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    assert leader is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "member_limit": 4,
            "seed": 50,
        },
    ).get_json()
    assert party is not None

    started = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 50},
    )
    assert started.status_code == 200
    started_payload = started.get_json()
    assert started_payload is not None

    refreshed_party = client.get(f"/api/parties/{party['code']}")
    assert refreshed_party.status_code == 200
    refreshed_payload = refreshed_party.get_json()
    assert refreshed_payload is not None
    assert refreshed_payload["active_match_id"] == started_payload["match_id"]
    assert refreshed_payload["active_match_finished"] is False

    second_start = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 50},
    )
    assert second_start.status_code == 400
    assert second_start.get_json() == {
        "error": "This party already has an active match"
    }


def test_casual_party_join_after_start_adds_player_to_active_match() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    leader = client.post(
        "/api/users",
        json={"name": "Leader", "guest": False, "elo": 1200},
    ).get_json()
    member = client.post(
        "/api/users",
        json={"name": "Member", "guest": False, "elo": 1180},
    ).get_json()
    late_joiner = client.post(
        "/api/users",
        json={"name": "LateJoiner", "guest": False, "elo": 1170},
    ).get_json()

    assert leader is not None and member is not None and late_joiner is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": leader["id"],
            "mode": "casual",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 600,
            "member_limit": 3,
            "seed": 51,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": member["id"]},
    )
    assert joined.status_code == 200

    started = client.post(
        f"/api/parties/{party['code']}/start",
        json={"user_id": leader["id"], "seed": 51},
    ).get_json()
    assert started is not None

    late_join = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": late_joiner["id"]},
    )
    assert late_join.status_code == 200
    late_party_payload = late_join.get_json()
    assert late_party_payload is not None
    assert late_party_payload["active_match_id"] == started["match_id"]

    refreshed_match = client.get(f"/api/matches/{started['match_id']}").get_json()
    assert refreshed_match is not None
    standing_user_ids = {row["user_id"] for row in refreshed_match["standings"]}
    assert late_joiner["id"] in standing_user_ids

    late_test = client.post(
        f"/api/matches/{started['match_id']}/test",
        json={"user_id": late_joiner["id"], "code": "x = 1"},
    )
    assert late_test.status_code == 200
    late_test_payload = late_test.get_json()
    assert late_test_payload is not None
    assert late_test_payload["verdict"] == "error"


def test_hint_unlock_sequence_and_submit_flow() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    user = client.post("/api/users", json={"name": "Ada", "guest": False}).get_json()
    assert user is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": user["id"],
            "mode": "zen",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "seed": 3,
        },
    ).get_json()
    assert party is not None

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": 3, "user_id": user["id"]},
    ).get_json()
    assert match is not None
    assert isinstance(match["free_hint"], str)
    assert match["free_hint"]

    hint1 = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"]},
    )
    hint2 = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"]},
    )
    hint3 = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"]},
    )
    no_more_hints = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"]},
    )

    assert hint1.status_code == 200
    assert hint2.status_code == 200
    assert hint3.status_code == 400
    assert no_more_hints.status_code == 400

    hint1_payload = hint1.get_json()
    hint2_payload = hint2.get_json()
    hint3_payload = hint3.get_json()
    assert hint1_payload is not None
    assert hint2_payload is not None
    assert hint3_payload is not None
    assert hint1_payload["level"] == 2
    assert hint2_payload["level"] == 3
    assert hint3_payload == {"error": "All hints already used"}

    result = client.post(
        f"/api/matches/{match['match_id']}/submit",
        json={"user_id": user["id"], "code": "x = 1"},
    ).get_json()
    assert result is not None
    assert result["verdict"] == "error"


def test_sample_test_endpoint_runs_samples_only_and_returns_stdout() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    user, match = _start_single_player_match(client, seed=11)
    code = _sample_only_solution(match["sample_tests"])

    test_run = client.post(
        f"/api/matches/{match['match_id']}/test",
        json={"user_id": user["id"], "code": code},
    ).get_json()
    assert test_run is not None
    assert test_run["verdict"] == "accepted"
    assert test_run["hidden_total"] == 0
    assert "trace" in test_run["stdout"]

    submit_run = client.post(
        f"/api/matches/{match['match_id']}/submit",
        json={"user_id": user["id"], "code": code},
    ).get_json()
    assert submit_run is not None
    assert submit_run["verdict"] == "wrong_answer"
    assert submit_run["first_failed_hidden_test"] is not None


def test_casual_match_auto_finishes_when_all_players_solve() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    leader, teammate, party, match = _start_two_player_casual_match(client, seed=31)

    def _accepted_submission(
        code: str,
        sample_tests: Any,
        hidden_tests: Any,
        contract: Any,
        shared_inputs: tuple[Any, ...] = (),
        timeout_seconds: float = 1.0,
        include_hidden_tests: bool = True,
    ) -> JudgeResult:
        hidden_total = len(hidden_tests) if include_hidden_tests else 0
        return JudgeResult(
            verdict="accepted",
            sample_passed=len(sample_tests),
            sample_total=len(sample_tests),
            hidden_passed=hidden_total,
            hidden_total=hidden_total,
            runtime_ms=1,
        )

    original_judge_submission = store_module.judge_submission
    store_module.judge_submission = cast(Any, _accepted_submission)
    try:
        first_submit = client.post(
            f"/api/matches/{match['match_id']}/submit",
            json={
                "user_id": leader["id"],
                "code": "def solution(arg1):\n    return arg1\n",
            },
        ).get_json()
        second_submit = client.post(
            f"/api/matches/{match['match_id']}/submit",
            json={
                "user_id": teammate["id"],
                "code": "def solution(arg1):\n    return arg1\n",
            },
        ).get_json()
    finally:
        store_module.judge_submission = cast(Any, original_judge_submission)

    assert first_submit is not None
    assert second_submit is not None
    assert first_submit["finished"] is False
    assert second_submit["finished"] is True
    assert all(row["rating_delta"] == 0 for row in second_submit["standings"])

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["finished"] is True

    refreshed_party = client.get(f"/api/parties/{party['code']}").get_json()
    assert refreshed_party is not None
    assert refreshed_party["active_match_finished"] is True


def test_casual_match_auto_finishes_when_all_players_forfeit() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    leader, teammate, party, match = _start_two_player_casual_match(client, seed=32)

    first_forfeit = client.post(
        f"/api/matches/{match['match_id']}/forfeit",
        json={"user_id": leader["id"]},
    ).get_json()
    second_forfeit = client.post(
        f"/api/matches/{match['match_id']}/forfeit",
        json={"user_id": teammate["id"]},
    ).get_json()

    assert first_forfeit is not None
    assert second_forfeit is not None
    assert first_forfeit["finished"] is False
    assert second_forfeit["finished"] is True
    assert all(row["forfeited"] is True for row in second_forfeit["standings"])

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["finished"] is True

    refreshed_party = client.get(f"/api/parties/{party['code']}").get_json()
    assert refreshed_party is not None
    assert refreshed_party["active_match_finished"] is True


def test_ranked_forfeit_auto_finishes_and_awards_the_other_player() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    leader, opponent, _, match = _start_two_player_ranked_match(client, seed=39)

    forfeit_payload = client.post(
        f"/api/matches/{match['match_id']}/forfeit",
        json={"user_id": leader["id"]},
    ).get_json()

    assert forfeit_payload is not None
    assert forfeit_payload["finished"] is True

    first_place = forfeit_payload["standings"][0]
    second_place = forfeit_payload["standings"][1]
    assert first_place["user_id"] == opponent["id"]
    assert first_place["forfeited"] is False
    assert first_place["rating_delta"] > 0
    assert second_place["user_id"] == leader["id"]
    assert second_place["forfeited"] is True
    assert second_place["rating_delta"] < 0

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert refreshed_match["finished"] is True


def test_close_party_locks_active_match_and_blocks_actions() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    leader, teammate, party, match = _start_two_player_casual_match(client, seed=33)

    closed = client.post(
        f"/api/parties/{party['code']}/close",
        json={"user_id": leader["id"]},
    )
    assert closed.status_code == 200
    closed_payload = closed.get_json()
    assert closed_payload == {"ok": True, "match_locked": True}

    get_closed_party = client.get(f"/api/parties/{party['code']}")
    assert get_closed_party.status_code == 400
    assert get_closed_party.get_json() == {"error": "Party not found"}

    locked_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert locked_match is not None
    assert locked_match["locked"] is True
    assert locked_match["finished"] is False

    blocked_submit = client.post(
        f"/api/matches/{match['match_id']}/submit",
        json={
            "user_id": teammate["id"],
            "code": "def solution(arg1):\n    return arg1\n",
        },
    )
    assert blocked_submit.status_code == 400
    assert blocked_submit.get_json() == {"error": "This match has been closed"}


def test_promote_failed_hidden_test_caps_visible_samples_at_four() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    user, match = _start_single_player_match(client, seed=13)

    latest_samples = match["sample_tests"]
    for _ in range(5):
        code = _sample_only_solution(latest_samples)
        submit_run = client.post(
            f"/api/matches/{match['match_id']}/submit",
            json={"user_id": user["id"], "code": code},
        ).get_json()
        assert submit_run is not None
        assert submit_run["verdict"] == "wrong_answer"
        failed = submit_run["first_failed_hidden_test"]
        assert failed is not None

        promoted = client.post(
            f"/api/matches/{match['match_id']}/promote-failed-test",
            json={"user_id": user["id"]},
        ).get_json()
        assert promoted is not None

        latest_samples = promoted["sample_tests"]
        assert len(latest_samples) <= 4
        assert any(
            sample["input"] == failed["input_str"]
            and sample["output"] == failed["expected_output"]
            for sample in latest_samples
        )

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert len(refreshed_match["sample_tests"]) == 4


def test_sample_tests_can_be_added_updated_and_deleted() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()
    user, match = _start_single_player_match(client, seed=17)

    original_samples = match["sample_tests"]
    assert len(original_samples) == 3

    add_response = client.post(
        f"/api/matches/{match['match_id']}/sample-tests",
        json={
            "user_id": user["id"],
            "action": "add",
            "inputs": [original_samples[0]["inputs"][0]],
        },
    )
    assert add_response.status_code == 200
    add_payload = add_response.get_json()
    assert add_payload is not None
    assert len(add_payload["sample_tests"]) == 4

    examples = original_samples[0]["inputs"][1]
    assert isinstance(examples, list) and examples
    probe_pair = examples[0]
    assert isinstance(probe_pair, list) and len(probe_pair) == 2
    inferred_key = int(probe_pair[0]) ^ int(probe_pair[1])
    expected_added = (int(original_samples[0]["inputs"][0]) ^ inferred_key) & 0xFF
    assert add_payload["sample_tests"][-1]["expected"] == expected_added

    updated_value = (int(original_samples[0]["inputs"][0]) + 7) % 256
    expected_updated = (updated_value ^ inferred_key) & 0xFF

    update_response = client.post(
        f"/api/matches/{match['match_id']}/sample-tests",
        json={
            "user_id": user["id"],
            "action": "update",
            "index": 0,
            "inputs": [updated_value, examples],
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload is not None
    assert update_payload["sample_tests"][0]["expected"] == expected_updated

    delete_response = client.post(
        f"/api/matches/{match['match_id']}/sample-tests",
        json={
            "user_id": user["id"],
            "action": "delete",
            "index": 3,
        },
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload is not None
    assert len(delete_payload["sample_tests"]) == 3


def test_caesar_and_substitution_samples_allow_row_edits_but_keep_shared_arg_locked() -> (
    None
):
    scenarios = (
        ("medium", "crypto-shift-inference-v2"),
        ("hard", "crypto-substitution-inference-v2"),
    )

    for index, (difficulty, expected_template_key) in enumerate(scenarios, start=1):
        app = create_app(MemoryStore())
        client = app.test_client()
        user, match = _start_single_player_match(
            client,
            seed=60 + index,
            theme="Cryptography",
            difficulty=difficulty,
        )

        assert match["template_key"] == expected_template_key
        original_samples = match["sample_tests"]
        assert len(original_samples) == 3

        baseline_input = original_samples[0]["primary_inputs"][0]
        assert isinstance(baseline_input, str)

        added_input = f"{baseline_input} test"
        add_response = client.post(
            f"/api/matches/{match['match_id']}/sample-tests",
            json={
                "user_id": user["id"],
                "action": "add",
                "inputs": [added_input],
            },
        )
        assert add_response.status_code == 200
        add_payload = add_response.get_json()
        assert add_payload is not None
        assert len(add_payload["sample_tests"]) == 4
        assert add_payload["sample_tests"][-1]["primary_inputs"] == [added_input]

        updated_input = added_input.upper()
        update_response = client.post(
            f"/api/matches/{match['match_id']}/sample-tests",
            json={
                "user_id": user["id"],
                "action": "update",
                "index": 0,
                "inputs": [updated_input],
            },
        )
        assert update_response.status_code == 200
        update_payload = update_response.get_json()
        assert update_payload is not None
        assert update_payload["sample_tests"][0]["primary_inputs"] == [updated_input]

        delete_response = client.post(
            f"/api/matches/{match['match_id']}/sample-tests",
            json={
                "user_id": user["id"],
                "action": "delete",
                "index": 3,
            },
        )
        assert delete_response.status_code == 200
        delete_payload = delete_response.get_json()
        assert delete_payload is not None
        assert len(delete_payload["sample_tests"]) == 3

        blocked_shared_arg_update = client.post(
            f"/api/matches/{match['match_id']}/sample-tests",
            json={
                "user_id": user["id"],
                "action": "update",
                "index": 0,
                "inputs": [updated_input, []],
            },
        )
        assert blocked_shared_arg_update.status_code == 400
        assert blocked_shared_arg_update.get_json() == {
            "error": "shared sample inputs cannot be edited"
        }


def test_ranked_party_match_with_admin_uses_hardcoded_numeric_template() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    admin_user = _register_admin(client)
    opponent = client.post(
        "/api/users", json={"name": "RankedOpponent", "guest": False, "elo": 1000}
    ).get_json()
    assert opponent is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": admin_user["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "member_limit": 2,
            "seed": 91,
        },
    ).get_json()
    assert party is not None

    joined = client.post(
        f"/api/parties/{party['code']}/join",
        json={"user_id": opponent["id"]},
    )
    assert joined.status_code == 200

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": 91, "user_id": admin_user["id"]},
    ).get_json()
    assert match is not None
    assert match["template_key"] == "numeric-add-reversed-number-v1"
    assert match["theme"] == "Numeric"
    assert match["difficulty"] == "hard"


def test_ranked_queue_match_with_admin_uses_hardcoded_numeric_template() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    admin_user = _register_admin(client)
    opponent = client.post(
        "/api/users", json={"name": "QueueOpponent", "guest": False, "elo": 1000}
    ).get_json()
    assert opponent is not None

    first_join = client.post(
        "/api/ranked/queue",
        json={"user_id": admin_user["id"], "seed": 92},
    )
    assert first_join.status_code == 200

    second_join = client.post(
        "/api/ranked/queue",
        json={"user_id": opponent["id"], "seed": 92},
    )
    assert second_join.status_code == 200
    queue_payload = second_join.get_json()
    assert queue_payload is not None
    assert queue_payload["status"] == "matched"
    assert queue_payload["match"] is not None
    assert queue_payload["match"]["template_key"] == "numeric-add-reversed-number-v1"
    assert queue_payload["match"]["theme"] == "Numeric"
    assert queue_payload["match"]["difficulty"] == "hard"


def test_ranked_theme_rotation_uses_all_themes_before_repeat() -> None:
    data = MemoryStore()
    ranked_themes = [theme for theme in THEMES if theme != "AI"]
    leader = data.create_user(name="CycleLeader", guest=False, elo=1000)
    party = data.create_party(
        leader_id=leader.id,
        mode="ranked",
        theme=THEMES[0],
        difficulty="easy",
        time_limit_seconds=900,
    )

    seen: list[str] = []
    for seed in range(1, len(ranked_themes) + 1):
        match = data.start_match(code=party.code, requester_id=leader.id, seed=seed)
        seen.append(match.theme)
        data.finish_match(match_id=match.id)

    assert len(set(seen)) == len(ranked_themes)
    assert set(seen) == set(ranked_themes)
    assert "AI" not in seen

    next_match = data.start_match(
        code=party.code,
        requester_id=leader.id,
        seed=len(ranked_themes) + 10,
    )
    assert next_match.theme in ranked_themes


def test_ai_theme_avoids_recent_topics_for_same_user() -> None:
    data = MemoryStore()
    user = data.create_user(name="AIPilot", guest=False, elo=1000)
    party = data.create_party(
        leader_id=user.id,
        mode="zen",
        theme="AI",
        difficulty="hard",
        time_limit_seconds=900,
    )

    seen_topics: list[str] = []
    for _index in range(3):
        match = data.start_match(code=party.code, requester_id=user.id, seed=17)
        topic = match.puzzle.variables.get("topic_key")
        assert isinstance(topic, str) and topic
        assert topic not in seen_topics
        seen_topics.append(topic)
        data.finish_match(match_id=match.id)

    refreshed_user = data.users[user.id]
    assert refreshed_user.recent_ai_topics == seen_topics[-data._AI_TOPIC_QUEUE_LIMIT :]


def test_ranked_submit_auto_finishes_and_updates_elo() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    user = client.post(
        "/api/users", json={"name": "RankedAda", "guest": False, "elo": 1000}
    ).get_json()
    assert user is not None

    party = client.post(
        "/api/parties",
        json={
            "leader_id": user["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "seed": 21,
        },
    ).get_json()
    assert party is not None

    match = client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": 21, "user_id": user["id"]},
    ).get_json()
    assert match is not None

    def _accepted_submission(
        code: str,
        sample_tests: Any,
        hidden_tests: Any,
        contract: Any,
        shared_inputs: tuple[Any, ...] = (),
        timeout_seconds: float = 1.0,
        include_hidden_tests: bool = True,
    ) -> JudgeResult:
        hidden_total = len(hidden_tests) if include_hidden_tests else 0
        return JudgeResult(
            verdict="accepted",
            sample_passed=len(sample_tests),
            sample_total=len(sample_tests),
            hidden_passed=hidden_total,
            hidden_total=hidden_total,
            runtime_ms=1,
        )

    original_judge_submission = store_module.judge_submission
    store_module.judge_submission = cast(Any, _accepted_submission)
    try:
        submit_payload = client.post(
            f"/api/matches/{match['match_id']}/submit",
            json={
                "user_id": user["id"],
                "code": "def solution(arg1):\n    return arg1\n",
            },
        ).get_json()
    finally:
        store_module.judge_submission = cast(Any, original_judge_submission)

    assert submit_payload is not None
    self_row = next(
        row for row in submit_payload["standings"] if row["user_id"] == user["id"]
    )
    assert self_row["rating_delta"] != 0
    assert self_row["elo"] == 1000 + self_row["rating_delta"]


def test_sqlite_ranked_elo_persists_after_auto_finish(tmp_path: Path) -> None:
    db_path = tmp_path / "ranked.sqlite3"

    first_app = create_app(SqliteStore(str(db_path)))
    first_client = first_app.test_client()

    user = first_client.post(
        "/api/users", json={"name": "PersistElo", "guest": False, "elo": 1000}
    ).get_json()
    assert user is not None

    party = first_client.post(
        "/api/parties",
        json={
            "leader_id": user["id"],
            "mode": "ranked",
            "theme": THEMES[0],
            "difficulty": "easy",
            "time_limit_seconds": 900,
            "seed": 22,
        },
    ).get_json()
    assert party is not None

    match = first_client.post(
        f"/api/parties/{party['code']}/start",
        json={"seed": 22, "user_id": user["id"]},
    ).get_json()
    assert match is not None

    def _accepted_submission(
        code: str,
        sample_tests: Any,
        hidden_tests: Any,
        contract: Any,
        shared_inputs: tuple[Any, ...] = (),
        timeout_seconds: float = 1.0,
        include_hidden_tests: bool = True,
    ) -> JudgeResult:
        hidden_total = len(hidden_tests) if include_hidden_tests else 0
        return JudgeResult(
            verdict="accepted",
            sample_passed=len(sample_tests),
            sample_total=len(sample_tests),
            hidden_passed=hidden_total,
            hidden_total=hidden_total,
            runtime_ms=1,
        )

    original_judge_submission = store_module.judge_submission
    store_module.judge_submission = cast(Any, _accepted_submission)
    try:
        submit_payload = first_client.post(
            f"/api/matches/{match['match_id']}/submit",
            json={
                "user_id": user["id"],
                "code": "def solution(arg1):\n    return arg1\n",
            },
        ).get_json()
    finally:
        store_module.judge_submission = cast(Any, original_judge_submission)

    assert submit_payload is not None
    updated_elo = next(
        row["elo"]
        for row in submit_payload["standings"]
        if row["user_id"] == user["id"]
    )
    assert updated_elo > 1000

    second_app = create_app(SqliteStore(str(db_path)))
    second_client = second_app.test_client()
    leaderboard = second_client.get("/api/leaderboard?limit=1").get_json()
    assert leaderboard is not None
    assert leaderboard["leaderboard"][0]["name"] == "PersistElo"
    assert leaderboard["leaderboard"][0]["elo"] == updated_elo
