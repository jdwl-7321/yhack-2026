from pathlib import Path
from typing import Any

from app import create_app
from constants import THEMES
from store import MemoryStore, SqliteStore


def _start_single_player_match(client: Any, *, seed: int = 3) -> tuple[dict, dict]:
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
            "seed": seed,
        },
    ).get_json()
    assert party is not None

    match = client.post(
        f"/api/parties/{party['code']}/start", json={"seed": seed}
    ).get_json()
    assert match is not None
    return user, match


def _sample_only_solution(sample_tests: list[dict[str, str]]) -> str:
    branch_lines: list[str] = []
    for sample in sample_tests:
        branch_lines.extend(
            [
                f"    if input_str == {sample['input']!r}:",
                f"        return {sample['output']!r}",
            ]
        )

    branch_block = "\n".join(branch_lines)
    return (
        "def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:\n"
        "    print('trace', len(input_str))\n"
        f"{branch_block}\n"
        "    return ''\n"
    )


def test_auth_session_register_login_logout() -> None:
    app = create_app(MemoryStore())
    client = app.test_client()

    initial_session = client.get("/api/auth/session").get_json()
    assert initial_session == {"authenticated": False}

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
    assert client.get("/api/auth/session").get_json() == {"authenticated": False}

    login = client.post(
        "/api/auth/login",
        json={"name": "Ada", "password": "secret123"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/session").get_json()["authenticated"] is True


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
        f"/api/parties/{party['code']}/start", json={"seed": 7}
    ).get_json()
    assert match is not None
    assert match["mode"] == "casual"


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
        f"/api/parties/{party['code']}/start", json={"seed": 3}
    ).get_json()
    assert match is not None

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
    assert hint3.status_code == 200
    assert no_more_hints.status_code == 400

    hint1_payload = hint1.get_json()
    hint2_payload = hint2.get_json()
    hint3_payload = hint3.get_json()
    assert hint1_payload is not None
    assert hint2_payload is not None
    assert hint3_payload is not None
    assert hint1_payload["level"] == 1
    assert hint2_payload["level"] == 2
    assert hint3_payload["level"] == 3

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
        assert {
            "input": failed["input_str"],
            "output": failed["expected_output"],
        } in latest_samples

    refreshed_match = client.get(f"/api/matches/{match['match_id']}").get_json()
    assert refreshed_match is not None
    assert len(refreshed_match["sample_tests"]) == 4
