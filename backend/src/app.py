from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import threading
from time import time
from typing import Any, cast

from flask import Flask, jsonify, request, session
from flask_sock import Sock

from config import ADMIN_USERNAME, is_admin_username
from constants import THEMES
from judge import JudgeResult
from puzzle import (
    TestCase,
    format_case_input,
    format_value,
    generator_schema,
    invocation_inputs,
    solution_scaffold,
    template_source,
    template_source_path,
    to_json_value,
    update_template_source,
)
from rating import ranked_matchmaking_window
from store import (
    Match,
    MemoryStore,
    Party,
    PuzzleTemplateConfig,
    RankedQueueEntry,
    SqliteStore,
    User,
)
from domain_types import Difficulty, Mode

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "yhack.sqlite3"


class EventHub:
    def __init__(self) -> None:
        self._channels: dict[str, dict[int, Any]] = {}
        self._locks: dict[int, threading.Lock] = {}
        self._guard = threading.Lock()

    def subscribe(self, *, channel: str, ws: Any) -> None:
        ws_id = id(ws)
        with self._guard:
            subscribers = self._channels.setdefault(channel, {})
            subscribers[ws_id] = ws
            self._locks.setdefault(ws_id, threading.Lock())

    def unsubscribe(self, *, channel: str, ws: Any) -> None:
        ws_id = id(ws)
        with self._guard:
            subscribers = self._channels.get(channel)
            if subscribers is not None:
                subscribers.pop(ws_id, None)
                if not subscribers:
                    self._channels.pop(channel, None)
            self._cleanup_lock(ws_id)

    def unsubscribe_all(self, *, ws: Any) -> None:
        ws_id = id(ws)
        with self._guard:
            for channel in list(self._channels):
                subscribers = self._channels[channel]
                subscribers.pop(ws_id, None)
                if not subscribers:
                    self._channels.pop(channel, None)
            self._locks.pop(ws_id, None)

    def publish(self, *, channel: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        with self._guard:
            subscribers = list(self._channels.get(channel, {}).items())

        stale_ws: list[int] = []
        for ws_id, ws in subscribers:
            lock = self._locks.get(ws_id)
            if lock is None:
                stale_ws.append(ws_id)
                continue

            try:
                with lock:
                    ws.send(message)
            except Exception:
                stale_ws.append(ws_id)

        if not stale_ws:
            return

        with self._guard:
            for ws_id in stale_ws:
                for channel_name in list(self._channels):
                    channel_subscribers = self._channels[channel_name]
                    channel_subscribers.pop(ws_id, None)
                    if not channel_subscribers:
                        self._channels.pop(channel_name, None)
                self._locks.pop(ws_id, None)

    def _cleanup_lock(self, ws_id: int) -> None:
        for subscribers in self._channels.values():
            if ws_id in subscribers:
                return
        self._locks.pop(ws_id, None)


def _party_channel(code: str) -> str:
    return f"party:{code.upper()}"


def _match_channel(match_id: str) -> str:
    return f"match:{match_id}"


def create_app(store: MemoryStore | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("YHACK_SECRET_KEY", "dev-secret")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    sock = Sock(app)
    event_hub = EventHub()
    data = store or SqliteStore(os.environ.get("YHACK_DB_PATH", str(DEFAULT_DB_PATH)))
    app.config["store"] = data

    def publish_party_update(party: Party, *, event: str) -> None:
        event_hub.publish(
            channel=_party_channel(party.code),
            payload={
                "type": "party.updated",
                "event": event,
                "party": _party_payload(data, party),
            },
        )

    def publish_party_closed(party: Party) -> None:
        event_hub.publish(
            channel=_party_channel(party.code),
            payload={
                "type": "party.closed",
                "event": "closed",
                "code": party.code,
                "message": "Party lobby was closed by the leader",
            },
        )

    def publish_match_update(
        match: Match, *, event: str, include_samples: bool = False
    ) -> None:
        event_hub.publish(
            channel=_match_channel(match.id),
            payload={
                "type": "match.updated",
                "event": event,
                "match": _match_payload(
                    data,
                    match,
                    include_samples=include_samples,
                ),
            },
        )

        try:
            party = data.get_party(code=match.party_code)
        except ValueError:
            return

        publish_party_update(party, event=event)

    def session_user_id() -> str:
        value = session.get("user_id")
        if not isinstance(value, str) or not value:
            raise ValueError("Authentication required")
        return value

    def session_user() -> User:
        user = data.users.get(session_user_id())
        if user is None:
            session.pop("user_id", None)
            raise ValueError("Authentication required")
        return user

    def require_admin_user() -> User:
        user = session_user()
        if not is_admin_username(user.name):
            raise ValueError("Admin access required")
        return user

    def payload_user_id(payload: dict[str, Any]) -> str:
        explicit = payload.get("user_id")
        if isinstance(explicit, str) and explicit:
            return explicit
        return session_user_id()

    @sock.route("/ws/events")
    def events_socket(ws: Any) -> None:
        subscribed_channels: set[str] = set()
        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break

                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                action = payload.get("action")
                channel = str(payload.get("channel", "")).strip()

                if action == "ping":
                    ws.send(json.dumps({"type": "pong"}))
                    continue

                if action == "subscribe":
                    if not channel:
                        ws.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "message": "channel is required for subscribe",
                                }
                            )
                        )
                        continue

                    event_hub.subscribe(channel=channel, ws=ws)
                    subscribed_channels.add(channel)
                    ws.send(json.dumps({"type": "subscribed", "channel": channel}))
                    continue

                if action == "unsubscribe":
                    if not channel:
                        continue
                    event_hub.unsubscribe(channel=channel, ws=ws)
                    subscribed_channels.discard(channel)
                    ws.send(json.dumps({"type": "unsubscribed", "channel": channel}))
                    continue

                ws.send(json.dumps({"type": "error", "message": "Unsupported action"}))
        finally:
            for channel in list(subscribed_channels):
                event_hub.unsubscribe(channel=channel, ws=ws)
            event_hub.unsubscribe_all(ws=ws)

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

    @app.route("/api/leaderboard", methods=["GET"])
    def leaderboard() -> Any:
        raw_user_id = session.get("user_id")
        current_user_id = raw_user_id if isinstance(raw_user_id, str) else None
        raw_limit = request.args.get("limit")
        limit_value = _optional_int(raw_limit) if raw_limit is not None else None
        limit = 8 if limit_value is None else limit_value
        return jsonify(data.leaderboard(limit=limit, current_user_id=current_user_id))

    @app.route("/api/generator/schema", methods=["GET"])
    def schema() -> Any:
        return jsonify(generator_schema())

    @app.route("/api/auth/session", methods=["GET"])
    def auth_session() -> Any:
        user_id = session.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            return jsonify({"authenticated": False, "is_admin": False})

        user = data.users.get(user_id)
        if user is None:
            session.pop("user_id", None)
            return jsonify({"authenticated": False, "is_admin": False})

        return jsonify(
            {
                "authenticated": True,
                "user": _user_payload(user),
                "is_admin": is_admin_username(user.name),
            }
        )

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register() -> Any:
        payload = request.get_json(silent=True) or {}
        user = data.register_account(
            name=str(payload.get("name", "")),
            password=str(payload.get("password", "")),
        )
        session["user_id"] = user.id
        return jsonify(
            {"user": _user_payload(user), "is_admin": is_admin_username(user.name)}
        )

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login() -> Any:
        payload = request.get_json(silent=True) or {}
        user = data.authenticate(
            name=str(payload.get("name", "")),
            password=str(payload.get("password", "")),
        )
        session["user_id"] = user.id
        return jsonify(
            {"user": _user_payload(user), "is_admin": is_admin_username(user.name)}
        )

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout() -> Any:
        session.pop("user_id", None)
        return jsonify({"ok": True})

    @app.route("/api/auth/password", methods=["POST"])
    def auth_change_password() -> Any:
        payload = request.get_json(silent=True) or {}
        data.change_password(
            user_id=session_user_id(),
            current_password=str(payload.get("current_password", "")),
            new_password=str(payload.get("new_password", "")),
        )
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

    @app.route("/api/admin/dashboard", methods=["GET"])
    def admin_dashboard() -> Any:
        require_admin_user()
        users = sorted(
            data.users.values(),
            key=lambda user: (-user.elo, user.name.casefold(), user.id),
        )
        active_matches = sorted(
            (match for match in data.matches.values() if not match.finished),
            key=lambda match: match.created_at,
            reverse=True,
        )
        return jsonify(
            {
                "admin_username": ADMIN_USERNAME,
                "users": [_user_payload(user) for user in users],
                "active_matches": [
                    _admin_match_payload(data, match) for match in active_matches
                ],
                "puzzle_templates": [
                    _admin_puzzle_template_payload(template)
                    for template in data.admin_list_puzzle_templates()
                ],
                "missing_puzzle_template_keys": (
                    data.admin_missing_puzzle_template_keys()
                ),
            }
        )

    @app.route("/api/admin/elo/reset", methods=["POST"])
    def admin_reset_elo() -> Any:
        require_admin_user()
        updated_users = data.admin_reset_all_elos(elo=1000)
        return jsonify({"ok": True, "updated_users": updated_users, "elo": 1000})

    @app.route("/api/admin/users/<user_id>/elo", methods=["POST"])
    def admin_set_player_elo(user_id: str) -> Any:
        require_admin_user()
        payload = request.get_json(silent=True) or {}
        if "elo" not in payload:
            raise ValueError("elo is required")
        user = data.admin_set_user_elo(user_id=user_id, elo=int(payload["elo"]))
        return jsonify({"user": _user_payload(user)})

    @app.route("/api/admin/users/<user_id>", methods=["DELETE"])
    def admin_delete_user(user_id: str) -> Any:
        admin_user = require_admin_user()
        if admin_user.id == user_id:
            raise ValueError("Admin account cannot delete itself")

        deleted_user, cancelled_matches, updated_parties = data.admin_delete_user(
            user_id=user_id
        )
        cancelled_party_codes: set[str] = set()
        for cancelled_match in cancelled_matches:
            publish_match_update(cancelled_match, event="admin_cancelled")
            if cancelled_match.party_code:
                cancelled_party_codes.add(cancelled_match.party_code)

        for party in updated_parties:
            if party.code in cancelled_party_codes:
                continue
            publish_party_update(party, event="admin_member_removed")

        return jsonify(
            {
                "ok": True,
                "deleted_user": _user_payload(deleted_user),
                "cancelled_match_ids": [match.id for match in cancelled_matches],
            }
        )

    @app.route("/api/admin/matches/<match_id>/cancel", methods=["POST"])
    def admin_cancel_match(match_id: str) -> Any:
        require_admin_user()
        match = data.admin_cancel_match(match_id=match_id)
        publish_match_update(match, event="admin_cancelled")
        return jsonify({"match": _admin_match_payload(data, match)})

    @app.route("/api/admin/puzzles", methods=["POST"])
    def admin_create_puzzle_template() -> Any:
        require_admin_user()
        payload = request.get_json(silent=True) or {}
        template_key = str(payload.get("template_key", "")).strip()
        if not template_key:
            raise ValueError("template_key is required")

        template = data.admin_create_puzzle_template(template_key=template_key)
        return jsonify({"puzzle_template": _admin_puzzle_template_payload(template)})

    @app.route("/api/admin/puzzles/<template_key>", methods=["POST"])
    def admin_update_puzzle_template(template_key: str) -> Any:
        require_admin_user()
        payload = request.get_json(silent=True) or {}

        required_fields = (
            "theme",
            "difficulty",
            "prompt",
            "hint_level_1",
            "hint_level_2",
            "hint_level_3",
            "enabled",
        )
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"{field} is required")

        raw_source_code = payload.get("source_code")
        if raw_source_code is not None:
            update_template_source(
                template_key=template_key,
                source_code=str(raw_source_code),
            )

        template = data.admin_update_puzzle_template(
            template_key=template_key,
            theme=str(payload["theme"]),
            difficulty=_parse_difficulty(payload["difficulty"]),
            prompt=str(payload["prompt"]),
            hint_level_1=str(payload["hint_level_1"]),
            hint_level_2=str(payload["hint_level_2"]),
            hint_level_3=str(payload["hint_level_3"]),
            enabled=_parse_bool(payload["enabled"], field_name="enabled"),
        )
        return jsonify({"puzzle_template": _admin_puzzle_template_payload(template)})

    @app.route("/api/admin/puzzles/<template_key>", methods=["DELETE"])
    def admin_delete_puzzle_template(template_key: str) -> Any:
        require_admin_user()
        deleted = data.admin_delete_puzzle_template(template_key=template_key)
        return jsonify({"deleted": _admin_puzzle_template_payload(deleted)})

    @app.route("/api/parties", methods=["POST"])
    def create_party() -> Any:
        payload = request.get_json(silent=True) or {}
        mode = _parse_mode(payload.get("mode"))
        difficulty = _parse_difficulty(payload.get("difficulty", "easy"))
        member_limit_raw = payload.get("member_limit", payload.get("party_limit"))
        party = data.create_party(
            leader_id=str(payload.get("leader_id", "")) or session_user_id(),
            mode=mode,
            theme=str(payload.get("theme", THEMES[0])),
            difficulty=difficulty,
            time_limit_seconds=int(payload.get("time_limit_seconds", 900)),
            member_limit=(
                _optional_int(member_limit_raw)
                if member_limit_raw is not None
                else None
            ),
            seed=_optional_int(payload.get("seed")),
        )
        publish_party_update(party, event="created")
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>", methods=["GET"])
    def get_party(code: str) -> Any:
        party = data.get_party(code=code)
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/join", methods=["POST"])
    def join_party(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        user_id = payload_user_id(payload)
        party = data.join_party(code=code, user_id=user_id)
        publish_party_update(party, event="member_joined")

        if party.active_match_id is not None:
            match = data.matches.get(party.active_match_id)
            if (
                match is not None
                and match.mode == "casual"
                and not match.finished
                and not match.locked
                and user_id in match.players
            ):
                publish_match_update(match, event="member_joined")

        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/limit", methods=["POST"])
    def set_party_limit(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        member_limit_raw = payload.get("member_limit", payload.get("party_limit"))
        if member_limit_raw is None:
            raise ValueError("member_limit is required")

        party = data.set_party_limit(
            code=code,
            leader_id=payload_user_id(payload),
            member_limit=int(member_limit_raw),
        )
        publish_party_update(party, event="limit_updated")
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/settings", methods=["POST"])
    def set_party_settings(code: str) -> Any:
        payload = request.get_json(silent=True) or {}

        if "theme" not in payload:
            raise ValueError("theme is required")
        if "difficulty" not in payload:
            raise ValueError("difficulty is required")
        if "time_limit_seconds" not in payload:
            raise ValueError("time_limit_seconds is required")

        party = data.set_party_settings(
            code=code,
            leader_id=payload_user_id(payload),
            theme=str(payload.get("theme", THEMES[0])),
            difficulty=_parse_difficulty(payload.get("difficulty")),
            time_limit_seconds=int(payload.get("time_limit_seconds", 900)),
            seed=_optional_int(payload.get("seed")),
        )
        publish_party_update(party, event="settings_updated")
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/add-time", methods=["POST"])
    def add_party_time(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        party, updated_match = data.add_party_time(
            code=code,
            leader_id=payload_user_id(payload),
            add_seconds=int(payload.get("add_seconds", 300)),
        )
        if updated_match is not None:
            publish_match_update(updated_match, event="time_extended")
        publish_party_update(party, event="time_extended")
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/kick", methods=["POST"])
    def kick_party_member(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        member_id = str(payload.get("member_id", "")).strip()
        if not member_id:
            raise ValueError("member_id is required")

        party = data.kick_party_member(
            code=code,
            leader_id=payload_user_id(payload),
            member_id=member_id,
        )
        publish_party_update(party, event="member_kicked")
        return jsonify(_party_payload(data, party))

    @app.route("/api/parties/<code>/close", methods=["POST"])
    def close_party(code: str) -> Any:
        payload = request.get_json(silent=True) or {}
        closed_party, locked_match = data.close_party(
            code=code,
            leader_id=payload_user_id(payload),
        )
        if locked_match is not None:
            publish_match_update(locked_match, event="lobby_closed")
        publish_party_closed(closed_party)
        return jsonify({"ok": True, "match_locked": locked_match is not None})

    @app.route("/api/parties/<code>/start", methods=["POST"])
    def start_match(code: str) -> Any:
        payload = request.get_json(silent=True) or {}

        theme: str | None = None
        difficulty: Difficulty | None = None
        time_limit_seconds: int | None = None

        has_custom_settings = any(
            field in payload for field in ("theme", "difficulty", "time_limit_seconds")
        )
        if has_custom_settings:
            if "theme" not in payload:
                raise ValueError("theme is required")
            if "difficulty" not in payload:
                raise ValueError("difficulty is required")
            if "time_limit_seconds" not in payload:
                raise ValueError("time_limit_seconds is required")

            theme = str(payload.get("theme", THEMES[0]))
            difficulty = _parse_difficulty(payload.get("difficulty"))
            time_limit_seconds = int(payload.get("time_limit_seconds", 900))

        match = data.start_match(
            code=code,
            requester_id=payload_user_id(payload),
            seed=_optional_int(payload.get("seed")),
            theme=theme,
            difficulty=difficulty,
            time_limit_seconds=time_limit_seconds,
        )
        publish_match_update(match, event="started")
        return jsonify(_match_payload(data, match))

    @app.route("/api/ranked/queue", methods=["GET"])
    def ranked_queue_status() -> Any:
        entry = data.ranked_queue_status(user_id=session_user_id())
        return jsonify(_ranked_queue_payload(data, entry))

    @app.route("/api/ranked/queue", methods=["POST"])
    def join_ranked_queue() -> Any:
        payload = request.get_json(silent=True) or {}
        entry = data.join_ranked_queue(
            user_id=payload_user_id(payload),
            seed=_optional_int(payload.get("seed")),
        )
        return jsonify(_ranked_queue_payload(data, entry))

    @app.route("/api/ranked/queue/leave", methods=["POST"])
    def leave_ranked_queue() -> Any:
        payload = request.get_json(silent=True) or {}
        data.leave_ranked_queue(user_id=payload_user_id(payload))
        return jsonify(_ranked_queue_payload(data, None))

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
        match = data.get_match(match_id=match_id)
        publish_match_update(match, event="submission")
        return jsonify(
            {
                **_judge_result_payload(result),
                "sample_tests": _sample_tests_payload(match),
                "finished": match.finished,
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
        publish_match_update(data.get_match(match_id=match_id), event="sample_test")
        return jsonify(
            {
                **_judge_result_payload(result),
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
        match = data.get_match(match_id=match_id)
        return jsonify(
            {
                "sample_tests": _sample_tests_payload_from_cases(
                    sample_tests,
                    shared_inputs=match.puzzle.shared_inputs,
                )
            }
        )

    @app.route("/api/matches/<match_id>/sample-tests", methods=["POST"])
    def manage_sample_tests(match_id: str) -> Any:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip().lower()
        user_id = payload_user_id(payload)

        if action == "add":
            raw_inputs = payload.get("inputs")
            if not isinstance(raw_inputs, list):
                raise ValueError("inputs must be a list")

            sample_tests = data.add_sample_test(
                match_id=match_id,
                user_id=user_id,
                inputs=raw_inputs,
            )
        elif action == "update":
            raw_index = payload.get("index")
            if raw_index is None:
                raise ValueError("index is required")
            raw_inputs = payload.get("inputs")
            if not isinstance(raw_inputs, list):
                raise ValueError("inputs must be a list")

            sample_tests = data.update_sample_test(
                match_id=match_id,
                user_id=user_id,
                index=int(raw_index),
                inputs=raw_inputs,
            )
        elif action == "delete":
            raw_index = payload.get("index")
            if raw_index is None:
                raise ValueError("index is required")

            sample_tests = data.delete_sample_test(
                match_id=match_id,
                user_id=user_id,
                index=int(raw_index),
            )
        else:
            raise ValueError("action must be one of: add, update, delete")

        match = data.get_match(match_id=match_id)
        publish_match_update(match, event="sample_tests_updated", include_samples=True)
        return jsonify(
            {
                "sample_tests": _sample_tests_payload_from_cases(
                    sample_tests,
                    shared_inputs=match.puzzle.shared_inputs,
                ),
                "standings": data.standings(match_id=match_id),
            }
        )

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
        match = data.get_match(match_id=match_id)
        publish_match_update(match, event="forfeit")
        return jsonify(
            {
                "finished": match.finished,
                "standings": data.standings(match_id=match_id),
            }
        )

    @app.route("/api/matches/<match_id>/finish", methods=["POST"])
    def finish(match_id: str) -> Any:
        deltas = data.finish_match(match_id=match_id)
        publish_match_update(data.get_match(match_id=match_id), event="finished")
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


def _parse_bool(raw: object, *, field_name: str) -> bool:
    if isinstance(raw, bool):
        return raw
    raise ValueError(f"{field_name} must be a boolean")


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
    members = [_user_payload(store.users[user_id]) for user_id in party.members]
    active_match = (
        store.matches.get(party.active_match_id) if party.active_match_id else None
    )
    return {
        "code": party.code,
        "join_code": party.code,
        "join_path": f"/?join={party.code}",
        "mode": party.mode,
        "leader_id": party.leader_id,
        "member_limit": party.member_limit,
        "is_full": len(members) >= party.member_limit,
        "active_match_id": party.active_match_id,
        "active_match_finished": active_match.finished if active_match else None,
        "settings": {
            "theme": party.settings.theme,
            "difficulty": party.settings.difficulty,
            "time_limit_seconds": party.settings.time_limit_seconds,
            "seed": party.settings.seed,
        },
        "members": members,
        "invite_link": f"/?join={party.code}",
    }


def _ranked_queue_payload(
    store: MemoryStore,
    entry: RankedQueueEntry | None,
) -> dict[str, Any]:
    if entry is None:
        return {
            "status": "idle",
            "queued_players": 0,
            "queued_at": None,
            "queued_elo": None,
            "search_range": None,
            "match": None,
        }

    queued_players = sum(
        1 for queue_entry in store.ranked_queue.values() if queue_entry.match_id is None
    )
    wait_seconds = max(0.0, time() - entry.joined_at)
    match = store.matches.get(entry.match_id) if entry.match_id is not None else None
    return {
        "status": "matched" if match is not None and not match.finished else "queued",
        "queued_players": queued_players,
        "queued_at": entry.joined_at,
        "queued_elo": entry.queued_elo,
        "search_range": ranked_matchmaking_window(wait_seconds),
        "match": (
            _match_payload(store, match)
            if match is not None and not match.finished
            else None
        ),
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
        "finished": match.finished,
        "locked": match.locked,
        "theme": match.theme,
        "difficulty": match.difficulty,
        "time_limit_seconds": match.time_limit_seconds,
        "created_at": match.created_at,
        "prompt": match.puzzle.prompt,
        "template_key": match.puzzle.template_key,
        "free_hint": match.puzzle.hint_level_1,
        "scaffold": solution_scaffold(match.puzzle.contract),
        "sample_tests": sample_tests if include_samples else [],
        "standings": store.standings(match_id=match.id),
    }
    return payload


def _sample_tests_payload(match: Match) -> list[dict[str, Any]]:
    return _sample_tests_payload_from_cases(
        match.puzzle.sample_tests,
        shared_inputs=match.puzzle.shared_inputs,
    )


def _sample_tests_payload_from_cases(
    cases: list[TestCase],
    *,
    shared_inputs: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    return [
        {
            "input": format_case_input(case.inputs),
            "output": format_value(case.output),
            "inputs": to_json_value(list(invocation_inputs(case, shared_inputs))),
            "primary_inputs": to_json_value(list(case.inputs)),
            "expected": to_json_value(case.output),
        }
        for case in cases
    ]


def _judge_result_payload(result: JudgeResult) -> dict[str, Any]:
    return {
        "verdict": result.verdict,
        "sample_passed": result.sample_passed,
        "sample_total": result.sample_total,
        "hidden_passed": result.hidden_passed,
        "hidden_total": result.hidden_total,
        "runtime_ms": result.runtime_ms,
        "message": result.message,
        "stdout": result.stdout,
        "first_failed_hidden_test": (
            None
            if result.first_failed_hidden_test is None
            else {
                "input_str": result.first_failed_hidden_test.input_str,
                "expected_output": result.first_failed_hidden_test.expected_output,
                "actual_output": result.first_failed_hidden_test.actual_output,
            }
        ),
    }


def _admin_match_payload(store: MemoryStore, match: Match) -> dict[str, Any]:
    players: list[dict[str, Any]] = []
    for user_id, player in match.players.items():
        user = store.users.get(user_id)
        players.append(
            {
                "user_id": user_id,
                "name": user.name if user is not None else "Deleted user",
                "guest": user.guest if user is not None else False,
                "elo": user.elo if user is not None else None,
                "solved": player.solved_at is not None,
                "forfeited": player.forfeited,
            }
        )

    return {
        "match_id": match.id,
        "party_code": match.party_code,
        "mode": match.mode,
        "theme": match.theme,
        "difficulty": match.difficulty,
        "time_limit_seconds": match.time_limit_seconds,
        "created_at": match.created_at,
        "locked": match.locked,
        "finished": match.finished,
        "players": players,
    }


def _admin_puzzle_template_payload(template: PuzzleTemplateConfig) -> dict[str, Any]:
    return {
        "template_key": template.template_key,
        "theme": template.theme,
        "difficulty": template.difficulty,
        "prompt": template.prompt,
        "hint_level_1": template.hint_level_1,
        "hint_level_2": template.hint_level_2,
        "hint_level_3": template.hint_level_3,
        "enabled": template.enabled,
        "source_path": template_source_path(template.template_key),
        "source_code": template_source(template.template_key),
    }
