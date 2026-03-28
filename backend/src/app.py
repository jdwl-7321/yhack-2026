from __future__ import annotations

from dataclasses import asdict
import os
from typing import Any, cast

from flask import Flask, jsonify, request, session

from constants import THEMES
from puzzle import TestCase, generator_schema
from store import Match, MemoryStore, Party, User
from domain_types import Difficulty, Mode

SOLUTION_SCAFFOLD = 'def solution(input_str: str) -> str:\n    return ""\n'


def create_app(store: MemoryStore | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("YHACK_SECRET_KEY", "dev-secret")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    data = store or MemoryStore()

    def session_user_id() -> str:
        value = session.get("user_id")
        if not isinstance(value, str) or not value:
            raise ValueError("Authentication required")
        return value

    def payload_user_id(payload: dict[str, Any]) -> str:
        explicit = payload.get("user_id")
        if isinstance(explicit, str) and explicit:
            return explicit
        return session_user_id()

    @app.after_request
    def add_cors_headers(response: Any) -> Any:
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.errorhandler(ValueError)
    def handle_value_error(exc: ValueError) -> tuple[Any, int]:
        return jsonify({"error": str(exc)}), 400

    @app.route("/api/health", methods=["GET"])
    def health() -> Any:
        return jsonify({"ok": True})

    @app.route("/api/themes", methods=["GET"])
    def themes() -> Any:
        return jsonify({"themes": THEMES})

    @app.route("/api/generator/schema", methods=["GET"])
    def schema() -> Any:
        return jsonify(generator_schema())

    @app.route("/api/auth/session", methods=["GET"])
    def auth_session() -> Any:
        user_id = session.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            return jsonify({"authenticated": False})

        user = data.users.get(user_id)
        if user is None:
            session.pop("user_id", None)
            return jsonify({"authenticated": False})

        return jsonify({"authenticated": True, "user": _user_payload(user)})

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register() -> Any:
        payload = request.get_json(silent=True) or {}
        user = data.register_account(
            name=str(payload.get("name", "")),
            password=str(payload.get("password", "")),
        )
        session["user_id"] = user.id
        return jsonify({"user": _user_payload(user)})

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login() -> Any:
        payload = request.get_json(silent=True) or {}
        user = data.authenticate(
            name=str(payload.get("name", "")),
            password=str(payload.get("password", "")),
        )
        session["user_id"] = user.id
        return jsonify({"user": _user_payload(user)})

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout() -> Any:
        session.pop("user_id", None)
        return jsonify({"ok": True})

    @app.route("/api/users", methods=["POST"])
    def create_user() -> Any:
        payload = request.get_json(silent=True) or {}
        user = data.create_user(
            name=str(payload.get("name", "Player")),
            guest=bool(payload.get("guest", True)),
            elo=int(payload.get("elo", 1000)),
        )
        return jsonify(_user_payload(user))

    @app.route("/api/parties", methods=["POST"])
    def create_party() -> Any:
        payload = request.get_json(silent=True) or {}
        mode = _parse_mode(payload.get("mode"))
        difficulty = _parse_difficulty(payload.get("difficulty"))
        party = data.create_party(
            leader_id=str(payload.get("leader_id", "")) or session_user_id(),
            mode=mode,
            theme=str(payload.get("theme", THEMES[0])),
            difficulty=difficulty,
            time_limit_seconds=int(payload.get("time_limit_seconds", 900)),
            seed=_optional_int(payload.get("seed")),
        )
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/join", methods=["POST"])
    def join_party(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        party = data.join_party(code=code, user_id=payload_user_id(payload))
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/start", methods=["POST"])
    def start_match(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        match = data.start_match(code=code, seed=_optional_int(payload.get("seed")))
        return jsonify(_match_payload(data, match))

    @app.route("/api/matches/<match_id>", methods=["GET"])
    def get_match(match_id: str) -> Any:
        match = data.get_match(match_id=match_id)
        return jsonify(_match_payload(data, match, include_samples=True))

    @app.route("/api/matches/<match_id>/submit", methods=["POST"])
    def submit(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        result = data.submit(
            match_id=match_id,
            user_id=payload_user_id(payload),
            code=str(payload.get("code", "")),
        )
        return jsonify(
            {
                **asdict(result),
                "sample_tests": _sample_tests_payload(
                    data.get_match(match_id=match_id)
                ),
                "standings": data.standings(match_id=match_id),
            }
        )

    @app.route("/api/matches/<match_id>/test", methods=["POST"])
    def test_samples(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        result = data.test_samples(
            match_id=match_id,
            user_id=payload_user_id(payload),
            code=str(payload.get("code", "")),
        )
        return jsonify(
            {
                **asdict(result),
                "sample_tests": _sample_tests_payload(
                    data.get_match(match_id=match_id)
                ),
                "standings": data.standings(match_id=match_id),
            }
        )

    @app.route("/api/matches/<match_id>/promote-failed-test", methods=["POST"])
    def promote_failed_test(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        sample_tests = data.promote_failed_hidden_test(
            match_id=match_id,
            user_id=payload_user_id(payload),
        )
        return jsonify({"sample_tests": _sample_tests_payload_from_cases(sample_tests)})

    @app.route("/api/matches/<match_id>/hint", methods=["POST"])
    def hint(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        level, text = data.request_hint(
            match_id=match_id,
            user_id=payload_user_id(payload),
        )
        return jsonify({"level": level, "hint": text})

    @app.route("/api/matches/<match_id>/forfeit", methods=["POST"])
    def forfeit(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        data.forfeit(match_id=match_id, user_id=payload_user_id(payload))
        return jsonify({"standings": data.standings(match_id=match_id)})

    @app.route("/api/matches/<match_id>/finish", methods=["POST"])
    def finish(match_id: str) -> Any:
        deltas = data.finish_match(match_id=match_id)
        return jsonify(
            {"rating_deltas": deltas, "standings": data.standings(match_id=match_id)}
        )

    return app


def main() -> None:
    create_app().run(host="0.0.0.0", port=5000, debug=True)


def _parse_mode(raw: object) -> Mode:
    if isinstance(raw, str) and raw in {"zen", "casual", "ranked"}:
        return cast(Mode, raw)
    raise ValueError("mode must be one of: zen, casual, ranked")


def _parse_difficulty(raw: object) -> Difficulty:
    if isinstance(raw, str) and raw in {"easy", "medium", "hard", "expert"}:
        return cast(Difficulty, raw)
    raise ValueError("difficulty must be one of: easy, medium, hard, expert")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError("Expected an integer-like value")


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "guest": user.guest,
        "elo": user.elo,
    }


def _party_payload(store: MemoryStore, party: Party) -> dict[str, Any]:
    return {
        "code": party.code,
        "mode": party.mode,
        "leader_id": party.leader_id,
        "settings": {
            "theme": party.settings.theme,
            "difficulty": party.settings.difficulty,
            "time_limit_seconds": party.settings.time_limit_seconds,
            "seed": party.settings.seed,
        },
        "members": [_user_payload(store.users[user_id]) for user_id in party.members],
        "invite_link": f"/join/{party.code}",
    }


def _match_payload(
    store: MemoryStore,
    match: Match,
    *,
    include_samples: bool = True,
) -> dict[str, Any]:
    sample_tests = _sample_tests_payload(match)

    payload: dict[str, Any] = {
        "match_id": match.id,
        "party_code": match.party_code,
        "mode": match.mode,
        "theme": match.theme,
        "difficulty": match.difficulty,
        "time_limit_seconds": match.time_limit_seconds,
        "created_at": match.created_at,
        "prompt": match.puzzle.prompt,
        "scaffold": SOLUTION_SCAFFOLD,
        "sample_tests": sample_tests if include_samples else [],
        "standings": store.standings(match_id=match.id),
    }
    return payload


def _sample_tests_payload(match: Match) -> list[dict[str, str]]:
    return _sample_tests_payload_from_cases(match.puzzle.sample_tests)


def _sample_tests_payload_from_cases(cases: list[TestCase]) -> list[dict[str, str]]:
    return [{"input": case.input_str, "output": case.output_str} for case in cases]
