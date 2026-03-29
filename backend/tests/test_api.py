from pathlib import Path
from typing import Any, cast

from app import create_app
from constants import THEMES
from judge import JudgeResult
import store as store_module
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


def test_ranked_theme_rotation_uses_all_themes_before_repeat() -> None:
    data = MemoryStore()
    leader = data.create_user(name="CycleLeader", guest=False, elo=1000)
    party = data.create_party(
        leader_id=leader.id,
        mode="ranked",
        theme=THEMES[0],
        difficulty="easy",
        time_limit_seconds=900,
    )

    seen: list[str] = []
    for seed in range(1, len(THEMES) + 1):
        match = data.start_match(code=party.code, requester_id=leader.id, seed=seed)
        seen.append(match.theme)
        data.finish_match(match_id=match.id)

    assert len(set(seen)) == len(THEMES)
    assert set(seen) == set(THEMES)

    next_match = data.start_match(
        code=party.code,
        requester_id=leader.id,
        seed=len(THEMES) + 10,
    )
    assert next_match.theme in THEMES


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
