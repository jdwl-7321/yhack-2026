from yhack_backend.app import create_app
from yhack_backend.constants import THEMES
from yhack_backend.store import MemoryStore


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


def test_hint_levels_and_submit_flow() -> None:
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
        json={"user_id": user["id"], "level": 1},
    )
    hint2 = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"], "level": 2},
    )
    dup_hint = client.post(
        f"/api/matches/{match['match_id']}/hint",
        json={"user_id": user["id"], "level": 2},
    )

    assert hint1.status_code == 200
    assert hint2.status_code == 200
    assert dup_hint.status_code == 400

    result = client.post(
        f"/api/matches/{match['match_id']}/submit",
        json={"user_id": user["id"], "code": "x = 1"},
    ).get_json()
    assert result is not None
    assert result["verdict"] == "error"
