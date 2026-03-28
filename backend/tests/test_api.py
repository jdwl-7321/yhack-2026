from app import create_app
from constants import THEMES
from store import MemoryStore


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
