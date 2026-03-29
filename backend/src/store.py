from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import sqlite3
import string
from time import time
import uuid
from werkzeug.security import check_password_hash, generate_password_hash

from constants import THEMES
from judge import JudgeResult, judge_submission
from puzzle import (
    HardcodedPuzzleTemplate,
    PuzzleInstance,
    TestCase,
    expected_output_for_primary_inputs,
    generate_additional_hidden_test,
    generate_puzzle_from_template,
    hardcoded_puzzle_templates,
    to_json_value,
)
from rating import (
    RankedResult,
    assign_ranked_difficulty,
    elo_deltas,
    order_ranked_results,
    ranked_matchmaking_window,
    resolve_mode,
)
from domain_types import Difficulty, Mode


@dataclass(slots=True)
class User:
    id: str
    name: str
    guest: bool
    elo: int = 1000
    password_hash: str | None = None
    profile_image_url: str | None = None
    recent_ai_topics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PartySettings:
    theme: str
    difficulty: Difficulty
    time_limit_seconds: int
    seed: int | None = None


@dataclass(slots=True)
class Party:
    code: str
    mode: Mode
    leader_id: str
    settings: PartySettings
    member_limit: int
    active_match_id: str | None = None
    members: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MatchPlayer:
    user_id: str
    solved_at: float | None = None
    hidden_passed: int = 0
    best_score_at: float = 0.0
    hint_level: int = 0
    forfeited: bool = False
    hints_used: set[int] = field(default_factory=set)
    last_failed_hidden_test: TestCase | None = None


@dataclass(slots=True)
class Match:
    id: str
    party_code: str
    mode: Mode
    theme: str
    difficulty: Difficulty
    time_limit_seconds: int
    puzzle: PuzzleInstance
    created_at: float
    players: dict[str, MatchPlayer]
    submissions: list[JudgeResult] = field(default_factory=list)
    rating_deltas: dict[str, int] | None = None
    finished: bool = False
    locked: bool = False


@dataclass(slots=True)
class RankedQueueEntry:
    user_id: str
    queued_elo: int
    joined_at: float
    last_seen_at: float
    match_id: str | None = None


class MemoryStore:
    _RANKED_QUEUE_STALE_SECONDS = 20.0
    _AI_TOPIC_QUEUE_LIMIT = 6

    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.user_name_index: dict[str, str] = {}
        self.parties: dict[str, Party] = {}
        self.matches: dict[str, Match] = {}
        self.ranked_queue: dict[str, RankedQueueEntry] = {}
        self._ranked_used_themes: set[str] = set()

    def create_user(
        self,
        *,
        name: str,
        guest: bool,
        elo: int = 1000,
        password_hash: str | None = None,
        recent_ai_topics: list[str] | None = None,
    ) -> User:
        user = User(
            id=f"u_{uuid.uuid4().hex[:8]}",
            name=name.strip() or "Player",
            guest=guest,
            elo=elo,
            password_hash=password_hash,
            recent_ai_topics=list(recent_ai_topics or []),
        )
        self.users[user.id] = user
        return user

    def register_account(self, *, name: str, password: str) -> User:
        normalized_name = self._normalize_name(name)
        if normalized_name in self.user_name_index:
            raise ValueError("Display name is already registered")

        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        user = self.create_user(
            name=name,
            guest=False,
            elo=1000,
            password_hash=generate_password_hash(password),
        )
        self.user_name_index[normalized_name] = user.id
        return user

    def authenticate(self, *, name: str, password: str) -> User:
        normalized_name = self._normalize_name(name)
        user_id = self.user_name_index.get(normalized_name)
        if user_id is None:
            raise ValueError("Invalid credentials")

        user = self._require_user(user_id)
        if user.password_hash is None or not check_password_hash(
            user.password_hash, password
        ):
            raise ValueError("Invalid credentials")
        return user

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> User:
        user = self._require_user(user_id)
        if user.guest or user.password_hash is None:
            raise ValueError(
                "Password changes are only available for registered accounts"
            )
        if not check_password_hash(user.password_hash, current_password):
            raise ValueError("Current password is incorrect")
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters")

        user.password_hash = generate_password_hash(new_password)
        return user

    def update_profile_image(
        self,
        *,
        user_id: str,
        profile_image_url: str | None,
    ) -> User:
        user = self._require_user(user_id)
        user.profile_image_url = profile_image_url
        return user

    def create_party(
        self,
        *,
        leader_id: str,
        mode: Mode,
        theme: str,
        difficulty: Difficulty,
        time_limit_seconds: int,
        member_limit: int | None = None,
        seed: int | None = None,
    ) -> Party:
        if leader_id not in self.users:
            raise ValueError("Leader user does not exist")
        self._validate_party_settings(
            theme=theme,
            difficulty=difficulty,
            time_limit_seconds=time_limit_seconds,
        )

        resolved_member_limit = self._resolve_party_limit(
            mode=mode,
            member_limit=member_limit,
        )

        code = self._new_party_code()
        party = Party(
            code=code,
            mode=mode,
            leader_id=leader_id,
            settings=PartySettings(
                theme=theme,
                difficulty=difficulty,
                time_limit_seconds=time_limit_seconds,
                seed=seed,
            ),
            member_limit=resolved_member_limit,
            members=[leader_id],
        )
        self.parties[party.code] = party
        return party

    def get_party(self, *, code: str) -> Party:
        return self._require_party(code)

    def join_party(self, *, code: str, user_id: str) -> Party:
        party = self._require_party(code)
        if user_id not in self.users:
            raise ValueError("User does not exist")
        if user_id not in party.members:
            if len(party.members) >= party.member_limit:
                raise ValueError("Party is full")
            party.members.append(user_id)

        if party.mode == "casual" and party.active_match_id is not None:
            active_match = self.matches.get(party.active_match_id)
            if (
                active_match is not None
                and not active_match.finished
                and not active_match.locked
                and user_id not in active_match.players
            ):
                active_match.players[user_id] = MatchPlayer(
                    user_id=user_id,
                    hint_level=1,
                    hints_used={1},
                )
        return party

    def set_party_limit(
        self,
        *,
        code: str,
        leader_id: str,
        member_limit: int,
    ) -> Party:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        resolved_member_limit = self._resolve_party_limit(
            mode=party.mode,
            member_limit=member_limit,
        )
        if resolved_member_limit < len(party.members):
            raise ValueError("Party limit cannot be below current member count")

        party.member_limit = resolved_member_limit
        return party

    def set_party_settings(
        self,
        *,
        code: str,
        leader_id: str,
        theme: str,
        difficulty: Difficulty,
        time_limit_seconds: int,
        seed: int | None = None,
    ) -> Party:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        self._validate_party_settings(
            theme=theme,
            difficulty=difficulty,
            time_limit_seconds=time_limit_seconds,
        )

        party.settings.theme = theme
        party.settings.difficulty = difficulty
        party.settings.time_limit_seconds = time_limit_seconds
        party.settings.seed = seed
        return party

    def add_party_time(
        self,
        *,
        code: str,
        leader_id: str,
        add_seconds: int,
    ) -> tuple[Party, Match | None]:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        if party.mode not in {"casual", "zen"}:
            raise ValueError("Time can only be added in casual or zen parties")
        if add_seconds <= 0:
            raise ValueError("add_seconds must be positive")

        party.settings.time_limit_seconds += add_seconds

        updated_match: Match | None = None
        if party.active_match_id is not None:
            active_match = self.matches.get(party.active_match_id)
            if (
                active_match is not None
                and not active_match.finished
                and not active_match.locked
            ):
                active_match.time_limit_seconds += add_seconds
                updated_match = active_match

        return party, updated_match

    def kick_party_member(
        self,
        *,
        code: str,
        leader_id: str,
        member_id: str,
    ) -> Party:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        if member_id == party.leader_id:
            raise ValueError("Leader cannot be kicked")
        if member_id not in party.members:
            raise ValueError("Member is not in this party")

        party.members = [user_id for user_id in party.members if user_id != member_id]
        return party

    def close_party(self, *, code: str, leader_id: str) -> tuple[Party, Match | None]:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        locked_match: Match | None = None
        if party.active_match_id is not None:
            active_match = self.matches.get(party.active_match_id)
            if active_match is not None and not active_match.finished:
                active_match.locked = True
                locked_match = active_match

        party.active_match_id = None
        closed_party = Party(
            code=party.code,
            mode=party.mode,
            leader_id=party.leader_id,
            settings=PartySettings(
                theme=party.settings.theme,
                difficulty=party.settings.difficulty,
                time_limit_seconds=party.settings.time_limit_seconds,
                seed=party.settings.seed,
            ),
            member_limit=party.member_limit,
            active_match_id=None,
            members=list(party.members),
        )
        self.parties.pop(code, None)
        return closed_party, locked_match

    def start_match(
        self,
        *,
        code: str,
        requester_id: str | None = None,
        seed: int | None = None,
        theme: str | None = None,
        difficulty: Difficulty | None = None,
        time_limit_seconds: int | None = None,
    ) -> Match:
        party = self._require_party(code)
        if requester_id is not None and requester_id != party.leader_id:
            raise ValueError("Only the party leader can start the match")

        if party.active_match_id is not None:
            existing_match = self.matches.get(party.active_match_id)
            if existing_match is not None and not existing_match.finished:
                raise ValueError("This party already has an active match")

        members = [self._require_user(user_id) for user_id in party.members]

        effective_mode = resolve_mode(
            party.mode,
            has_guest=any(member.guest for member in members),
        )

        if effective_mode == "ranked":
            if (
                theme is not None
                or difficulty is not None
                or time_limit_seconds is not None
            ):
                raise ValueError("Ranked matches do not support custom settings")
            avg_elo = sum(member.elo for member in members) / max(1, len(members))
            match_difficulty = assign_ranked_difficulty(avg_elo)
            match_theme = self._choose_next_ranked_theme(seed=seed)
            match_time_limit_seconds = 3600
        else:
            match_theme = theme if theme is not None else party.settings.theme
            match_difficulty = (
                difficulty if difficulty is not None else party.settings.difficulty
            )
            match_time_limit_seconds = (
                time_limit_seconds
                if time_limit_seconds is not None
                else party.settings.time_limit_seconds
            )
            self._validate_party_settings(
                theme=match_theme,
                difficulty=match_difficulty,
                time_limit_seconds=match_time_limit_seconds,
            )
            party.settings.theme = match_theme
            party.settings.difficulty = match_difficulty
            party.settings.time_limit_seconds = match_time_limit_seconds

        match_seed = seed if seed is not None else random.randint(1, 10**9)
        puzzle = self._generate_match_puzzle(
            theme=match_theme,
            difficulty=match_difficulty,
            seed=match_seed,
            participant_user_ids=[member.id for member in members],
        )

        match = Match(
            id=f"m_{uuid.uuid4().hex[:10]}",
            party_code=code,
            mode=effective_mode,
            theme=match_theme,
            difficulty=match_difficulty,
            time_limit_seconds=match_time_limit_seconds,
            puzzle=puzzle,
            created_at=time(),
            players={
                user.id: MatchPlayer(user_id=user.id, hint_level=1, hints_used={1})
                for user in members
            },
        )

        self.matches[match.id] = match
        party.active_match_id = match.id
        return match

    def join_ranked_queue(
        self,
        *,
        user_id: str,
        seed: int | None = None,
    ) -> RankedQueueEntry:
        user = self._require_user(user_id)
        if user.guest:
            raise ValueError("Ranked matchmaking requires a registered account")
        if self._active_match_for_user(user_id) is not None:
            raise ValueError("Finish your current match before queueing again")

        now = time()
        self._purge_stale_ranked_queue(now=now)
        existing = self.ranked_queue.get(user_id)
        if existing is not None:
            existing.queued_elo = user.elo
            existing.last_seen_at = now
            if existing.match_id is not None:
                match = self.matches.get(existing.match_id)
                if match is not None and not match.finished:
                    return existing
                self.ranked_queue.pop(user_id, None)
                existing = None

        if existing is None:
            existing = RankedQueueEntry(
                user_id=user_id,
                queued_elo=user.elo,
                joined_at=now,
                last_seen_at=now,
            )
            self.ranked_queue[user_id] = existing

        self._attempt_ranked_match(entry=existing, seed=seed, now=now)
        return self.ranked_queue[user_id]

    def ranked_queue_status(self, *, user_id: str) -> RankedQueueEntry | None:
        now = time()
        self._purge_stale_ranked_queue(now=now)
        entry = self.ranked_queue.get(user_id)
        if entry is None:
            return None

        entry.queued_elo = self._require_user(user_id).elo
        entry.last_seen_at = now
        return entry

    def leave_ranked_queue(self, *, user_id: str) -> None:
        entry = self.ranked_queue.get(user_id)
        if entry is None:
            return
        if entry.match_id is not None:
            match = self.matches.get(entry.match_id)
            if match is not None and not match.finished:
                raise ValueError("A ranked match is already ready for you")
        self.ranked_queue.pop(user_id, None)

    def get_match(self, *, match_id: str) -> Match:
        return self._require_match(match_id)

    def submit(self, *, match_id: str, user_id: str, code: str) -> JudgeResult:
        match = self._require_match(match_id)
        if match.locked:
            raise ValueError("This match has been closed")
        player = self._require_player(match, user_id)
        if player.forfeited:
            raise ValueError("Player already forfeited")

        result = judge_submission(
            code=code,
            sample_tests=match.puzzle.sample_tests,
            hidden_tests=match.puzzle.hidden_tests,
            contract=match.puzzle.contract,
            shared_inputs=match.puzzle.shared_inputs,
        )

        player.last_failed_hidden_test = result.first_failed_hidden_case

        now = time()
        if result.hidden_passed >= player.hidden_passed:
            player.hidden_passed = result.hidden_passed
            player.best_score_at = now
        if result.verdict == "accepted" and player.solved_at is None:
            player.solved_at = now

        match.submissions.append(result)
        self._auto_finish_match(match)
        return result

    def test_samples(self, *, match_id: str, user_id: str, code: str) -> JudgeResult:
        match = self._require_match(match_id)
        if match.locked:
            raise ValueError("This match has been closed")
        player = self._require_player(match, user_id)
        if player.forfeited:
            raise ValueError("Player already forfeited")

        return judge_submission(
            code=code,
            sample_tests=match.puzzle.sample_tests,
            hidden_tests=match.puzzle.hidden_tests,
            contract=match.puzzle.contract,
            shared_inputs=match.puzzle.shared_inputs,
            include_hidden_tests=False,
        )

    def promote_failed_hidden_test(
        self, *, match_id: str, user_id: str
    ) -> list[TestCase]:
        match = self._require_match(match_id)
        if match.locked:
            raise ValueError("This match has been closed")
        player = self._require_player(match, user_id)
        failed = player.last_failed_hidden_test
        if failed is None:
            raise ValueError("No failed hidden test available yet")

        if failed not in match.puzzle.sample_tests:
            if len(match.puzzle.sample_tests) >= 4:
                match.puzzle.sample_tests.pop(0)
            match.puzzle.sample_tests.append(failed)

        removed = False
        for index, hidden_case in enumerate(match.puzzle.hidden_tests):
            if hidden_case == failed:
                match.puzzle.hidden_tests.pop(index)
                removed = True
                break

        if removed:
            replacement = generate_additional_hidden_test(
                theme=match.puzzle.theme,
                difficulty=match.puzzle.difficulty,
                variables=match.puzzle.variables,
                existing_cases=[
                    *match.puzzle.sample_tests,
                    *match.puzzle.hidden_tests,
                ],
                seed=random.randint(1, 10**9),
                template_key=match.puzzle.template_key,
            )
            match.puzzle.hidden_tests.append(replacement)

        player.last_failed_hidden_test = None
        return match.puzzle.sample_tests

    def add_sample_test(
        self,
        *,
        match_id: str,
        user_id: str,
        inputs: list[object],
    ) -> list[TestCase]:
        match = self._require_match(match_id)
        self._require_player(match, user_id)
        case = self._build_custom_sample_case(match=match, inputs=inputs)
        match.puzzle.sample_tests.append(case)
        return match.puzzle.sample_tests

    def update_sample_test(
        self,
        *,
        match_id: str,
        user_id: str,
        index: int,
        inputs: list[object],
    ) -> list[TestCase]:
        match = self._require_match(match_id)
        self._require_player(match, user_id)
        self._require_sample_test_index(match=match, index=index)
        case = self._build_custom_sample_case(match=match, inputs=inputs)
        match.puzzle.sample_tests[index] = case
        return match.puzzle.sample_tests

    def delete_sample_test(
        self,
        *,
        match_id: str,
        user_id: str,
        index: int,
    ) -> list[TestCase]:
        match = self._require_match(match_id)
        self._require_player(match, user_id)
        self._require_sample_test_index(match=match, index=index)
        match.puzzle.sample_tests.pop(index)
        return match.puzzle.sample_tests

    def request_hint(self, *, match_id: str, user_id: str) -> tuple[int, str]:
        match = self._require_match(match_id)
        if match.locked:
            raise ValueError("This match has been closed")
        player = self._require_player(match, user_id)
        if player.hint_level >= 3:
            raise ValueError("All hints already used")

        level = player.hint_level + 1
        hints_by_level = {
            1: match.puzzle.hint_level_1,
            2: match.puzzle.hint_level_2,
            3: match.puzzle.hint_level_3,
        }

        player.hints_used.add(level)
        player.hint_level = level
        return level, hints_by_level[level]

    def forfeit(self, *, match_id: str, user_id: str) -> None:
        match = self._require_match(match_id)
        if match.locked:
            raise ValueError("This match has been closed")
        player = self._require_player(match, user_id)
        player.forfeited = True
        self._auto_finish_match(match)

    def finish_match(self, *, match_id: str) -> dict[str, int]:
        match = self._require_match(match_id)
        if match.finished:
            return match.rating_deltas or {}

        match.finished = True
        if match.mode != "ranked":
            match.rating_deltas = {}
            return {}

        now = time()
        ranking_input: list[RankedResult] = []
        for player in match.players.values():
            user = self._require_user(player.user_id)
            ranking_input.append(
                RankedResult(
                    user_id=user.id,
                    elo=user.elo,
                    solved_at=player.solved_at,
                    hidden_passed=player.hidden_passed,
                    best_score_at=player.best_score_at or now,
                    hint_level=player.hint_level,
                    forfeited=player.forfeited,
                )
            )

        deltas = elo_deltas(ranking_input, match.difficulty)
        for user_id, delta in deltas.items():
            self.users[user_id].elo += delta

        for user_id in match.players:
            self.ranked_queue.pop(user_id, None)

        match.rating_deltas = deltas
        return deltas

    def standings(self, *, match_id: str) -> list[dict[str, object]]:
        match = self._require_match(match_id)
        now = time()
        ranking_input = [
            RankedResult(
                user_id=player.user_id,
                elo=self._require_user(player.user_id).elo,
                solved_at=player.solved_at,
                hidden_passed=player.hidden_passed,
                best_score_at=player.best_score_at or now,
                hint_level=player.hint_level,
                forfeited=player.forfeited,
            )
            for player in match.players.values()
        ]

        ordered = order_ranked_results(ranking_input)
        standings: list[dict[str, object]] = []
        for placement, ranked in enumerate(ordered, start=1):
            player = match.players[ranked.user_id]
            user = self.users[ranked.user_id]
            standings.append(
                {
                    "placement": placement,
                    "user_id": user.id,
                    "name": user.name,
                    "elo": user.elo,
                    "solved": player.solved_at is not None,
                    "hidden_passed": player.hidden_passed,
                    "hint_level": player.hint_level,
                    "forfeited": player.forfeited,
                    "rating_delta": (match.rating_deltas or {}).get(user.id, 0),
                }
            )

        return standings

    def leaderboard(
        self, *, limit: int = 10, current_user_id: str | None = None
    ) -> dict[str, object]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        ranked_users = sorted(
            (user for user in self.users.values() if not user.guest),
            key=lambda user: (-user.elo, user.name.casefold(), user.id),
        )

        top_entries: list[dict[str, object]] = []
        current_entry: dict[str, object] | None = None
        for placement, user in enumerate(ranked_users, start=1):
            entry = {
                "placement": placement,
                "user_id": user.id,
                "name": user.name,
                "elo": user.elo,
                "guest": user.guest,
                "profile_image_url": user.profile_image_url,
            }
            if placement <= limit:
                top_entries.append(entry)
            if user.id == current_user_id:
                current_entry = entry

        return {
            "leaderboard": top_entries,
            "current_user": current_entry,
            "total_players": len(ranked_users),
        }

    def admin_reset_all_elos(self, *, elo: int = 1000) -> int:
        if elo < 0:
            raise ValueError("elo must be non-negative")

        for user in self.users.values():
            user.elo = elo
        return len(self.users)

    def admin_set_user_elo(self, *, user_id: str, elo: int) -> User:
        if elo < 0:
            raise ValueError("elo must be non-negative")

        user = self._require_user(user_id)
        user.elo = elo
        return user

    def admin_list_puzzle_templates(self) -> list[HardcodedPuzzleTemplate]:
        return sorted(
            hardcoded_puzzle_templates(),
            key=lambda template: (
                template.theme,
                template.difficulty,
                template.template_key,
            ),
        )

    def admin_cancel_match(self, *, match_id: str) -> Match:
        match = self._require_match(match_id)
        if match.finished:
            raise ValueError("Match is already finished")

        match.finished = True
        match.locked = True
        match.rating_deltas = {}

        for player_user_id in list(match.players):
            self.ranked_queue.pop(player_user_id, None)

        if match.party_code:
            party = self.parties.get(match.party_code)
            if party is not None and party.active_match_id == match.id:
                party.active_match_id = None

        return match

    def admin_delete_user(
        self, *, user_id: str
    ) -> tuple[User, list[Match], list[Party]]:
        user = self._require_user(user_id)

        match_ids_to_cancel = [
            match.id
            for match in self.matches.values()
            if not match.finished and user_id in match.players
        ]
        cancelled_matches = [
            self.admin_cancel_match(match_id=match_id)
            for match_id in match_ids_to_cancel
        ]

        updated_parties: list[Party] = []
        for party_code, party in list(self.parties.items()):
            if user_id not in party.members:
                continue

            party.members = [
                member_id for member_id in party.members if member_id != user_id
            ]
            if not party.members:
                self.parties.pop(party_code, None)
                continue

            if party.leader_id == user_id:
                party.leader_id = party.members[0]

            if party.active_match_id is not None:
                active_match = self.matches.get(party.active_match_id)
                if active_match is None or active_match.finished:
                    party.active_match_id = None

            updated_parties.append(party)

        for match in self.matches.values():
            if user_id not in match.players:
                continue
            match.players.pop(user_id, None)
            if match.rating_deltas is not None:
                match.rating_deltas.pop(user_id, None)

        self.ranked_queue.pop(user_id, None)
        self._remove_user_name_index(user_id=user_id)
        self.users.pop(user_id, None)
        return user, cancelled_matches, updated_parties

    def _new_party_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choice(alphabet) for _ in range(6))
            if code not in self.parties:
                return code

    @staticmethod
    def _resolve_party_limit(*, mode: Mode, member_limit: int | None) -> int:
        if mode == "zen":
            return 1

        if member_limit is None:
            return 4

        if member_limit < 2:
            raise ValueError("Party limit must be at least 2")
        if member_limit > 16:
            raise ValueError("Party limit cannot exceed 16")
        return member_limit

    @staticmethod
    def _validate_party_settings(
        *,
        theme: str,
        difficulty: Difficulty,
        time_limit_seconds: int,
    ) -> None:
        if theme not in THEMES:
            raise ValueError("Theme must be from the hardcoded catalog")
        if difficulty not in {"easy", "medium", "hard", "expert"}:
            raise ValueError("Invalid difficulty")
        if time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be positive")

    def _generate_match_puzzle(
        self,
        *,
        theme: str,
        difficulty: Difficulty,
        seed: int,
        participant_user_ids: list[str] | None = None,
    ) -> PuzzleInstance:
        candidates = [
            template
            for template in hardcoded_puzzle_templates()
            if template.theme == theme and template.difficulty == difficulty
        ]
        if not candidates:
            raise ValueError(
                "No puzzle templates are available for this theme/difficulty"
            )

        selected = random.Random(seed).choice(candidates)

        if theme != "AI":
            return generate_puzzle_from_template(
                template_key=selected.template_key,
                theme=selected.theme,
                difficulty=selected.difficulty,
                seed=seed,
                prompt=selected.prompt,
                hint_level_1=selected.hint_level_1,
                hint_level_2=selected.hint_level_2,
                hint_level_3=selected.hint_level_3,
            )

        blocked_topics = self._blocked_ai_topics_for_users(participant_user_ids or [])
        for attempt in range(20):
            attempt_seed = seed + (attempt * 7907)
            puzzle = generate_puzzle_from_template(
                template_key=selected.template_key,
                theme=selected.theme,
                difficulty=selected.difficulty,
                seed=attempt_seed,
                prompt=selected.prompt,
                hint_level_1=selected.hint_level_1,
                hint_level_2=selected.hint_level_2,
                hint_level_3=selected.hint_level_3,
            )
            topic_key = self._ai_topic_key(puzzle)
            if topic_key in blocked_topics:
                continue
            self._record_ai_topic_for_users(
                participant_user_ids or [],
                topic_key=topic_key,
            )
            return puzzle

        raise ValueError("Unable to generate a novel AI puzzle topic for these players")

    def _blocked_ai_topics_for_users(self, user_ids: list[str]) -> set[str]:
        blocked: set[str] = set()
        for user_id in user_ids:
            user = self.users.get(user_id)
            if user is None:
                continue
            blocked.update(user.recent_ai_topics)
        return blocked

    @staticmethod
    def _ai_topic_key(puzzle: PuzzleInstance) -> str:
        candidate = puzzle.variables.get("topic_key")
        if isinstance(candidate, str) and candidate:
            return candidate
        fallback = puzzle.variables.get("operation")
        if isinstance(fallback, str) and fallback:
            return f"AI:{fallback}"
        return f"AI:{puzzle.template_key}"

    def _record_ai_topic_for_users(
        self, user_ids: list[str], *, topic_key: str
    ) -> None:
        if not topic_key:
            return

        for user_id in user_ids:
            user = self.users.get(user_id)
            if user is None:
                continue

            queue = [topic for topic in user.recent_ai_topics if topic != topic_key]
            queue.append(topic_key)
            user.recent_ai_topics = queue[-self._AI_TOPIC_QUEUE_LIMIT :]

    def _choose_next_ranked_theme(self, *, seed: int | None) -> str:
        ranked_themes = [theme for theme in THEMES if theme != "AI"]
        available = [
            theme for theme in ranked_themes if theme not in self._ranked_used_themes
        ]
        if not available:
            self._ranked_used_themes.clear()
            available = ranked_themes

        if not available:
            raise ValueError("No ranked themes are configured")

        chooser = random.Random(seed) if seed is not None else random
        chosen = chooser.choice(available)
        self._ranked_used_themes.add(chosen)
        return chosen

    @staticmethod
    def _require_party_leader(party: Party, leader_id: str) -> None:
        if party.leader_id != leader_id:
            raise ValueError("Only the party leader can do that")

    def _auto_finish_match(self, match: Match) -> None:
        if match.finished:
            return

        all_players_done = all(
            player.forfeited or player.solved_at is not None
            for player in match.players.values()
        )
        if all_players_done:
            self.finish_match(match_id=match.id)
            return

        if match.mode != "ranked":
            return

        active_players = [
            player for player in match.players.values() if not player.forfeited
        ]
        forfeited_count = len(match.players) - len(active_players)
        if forfeited_count > 0 and len(active_players) == 1:
            self.finish_match(match_id=match.id)

    def _attempt_ranked_match(
        self,
        *,
        entry: RankedQueueEntry,
        seed: int | None,
        now: float,
    ) -> Match | None:
        if entry.match_id is not None:
            match = self.matches.get(entry.match_id)
            if match is not None and not match.finished:
                return match
            entry.match_id = None

        best_candidate: RankedQueueEntry | None = None
        best_score: tuple[int, float, str] | None = None
        for candidate in self.ranked_queue.values():
            if candidate.user_id == entry.user_id or candidate.match_id is not None:
                continue

            elo_gap = abs(entry.queued_elo - candidate.queued_elo)
            entry_wait = max(0.0, now - entry.joined_at)
            candidate_wait = max(0.0, now - candidate.joined_at)
            max_gap = max(
                ranked_matchmaking_window(entry_wait),
                ranked_matchmaking_window(candidate_wait),
            )
            if elo_gap > max_gap:
                continue

            score = (elo_gap, candidate.joined_at, candidate.user_id)
            if best_score is None or score < best_score:
                best_candidate = candidate
                best_score = score

        if best_candidate is None:
            return None

        match = self._create_ranked_match(
            user_ids=[entry.user_id, best_candidate.user_id],
            seed=seed,
        )
        entry.match_id = match.id
        entry.last_seen_at = now
        best_candidate.match_id = match.id
        best_candidate.last_seen_at = now
        return match

    def _create_ranked_match(
        self,
        *,
        user_ids: list[str],
        seed: int | None,
    ) -> Match:
        members = [self._require_user(user_id) for user_id in user_ids]
        avg_elo = sum(member.elo for member in members) / max(1, len(members))
        difficulty = assign_ranked_difficulty(avg_elo)
        theme = self._choose_next_ranked_theme(seed=seed)
        match_seed = seed if seed is not None else random.randint(1, 10**9)
        puzzle = self._generate_match_puzzle(
            theme=theme,
            difficulty=difficulty,
            seed=match_seed,
            participant_user_ids=[member.id for member in members],
        )

        match = Match(
            id=f"m_{uuid.uuid4().hex[:10]}",
            party_code="",
            mode="ranked",
            theme=theme,
            difficulty=difficulty,
            time_limit_seconds=3600,
            puzzle=puzzle,
            created_at=time(),
            players={
                user.id: MatchPlayer(user_id=user.id, hint_level=1, hints_used={1})
                for user in members
            },
        )
        self.matches[match.id] = match
        return match

    def _active_match_for_user(self, user_id: str) -> Match | None:
        for match in self.matches.values():
            if match.finished:
                continue
            if user_id in match.players:
                return match
        return None

    def _purge_stale_ranked_queue(self, *, now: float) -> None:
        stale_user_ids = [
            user_id
            for user_id, entry in self.ranked_queue.items()
            if entry.match_id is None
            and now - entry.last_seen_at > self._RANKED_QUEUE_STALE_SECONDS
        ]
        for user_id in stale_user_ids:
            self.ranked_queue.pop(user_id, None)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip()
        if len(normalized) < 3:
            raise ValueError("Display name must be at least 3 characters")
        if len(normalized) > 24:
            raise ValueError("Display name must be 24 characters or less")
        return normalized.casefold()

    def _remove_user_name_index(self, *, user_id: str) -> None:
        for normalized_name, indexed_user_id in list(self.user_name_index.items()):
            if indexed_user_id == user_id:
                self.user_name_index.pop(normalized_name, None)

    def _require_user(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    @staticmethod
    def _require_sample_test_index(*, match: Match, index: int) -> None:
        if index < 0 or index >= len(match.puzzle.sample_tests):
            raise ValueError("sample test index out of range")

    @staticmethod
    def _validate_case_value(value: object) -> None:
        if isinstance(value, (str, int, float, bool)):
            return
        if isinstance(value, list):
            for item in value:
                MemoryStore._validate_case_value(item)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("sample test object keys must be strings")
                MemoryStore._validate_case_value(item)
            return
        raise ValueError(
            "sample test values must use JSON-compatible primitives, lists, and objects"
        )

    @staticmethod
    def _build_custom_sample_case(
        *,
        match: Match,
        inputs: list[object],
    ) -> TestCase:
        primary_arity = len(match.puzzle.contract.parameter_types) - len(
            match.puzzle.shared_inputs
        )
        total_arity = len(match.puzzle.contract.parameter_types)
        if len(inputs) == total_arity and total_arity != primary_arity:
            expected_shared_inputs = list(match.puzzle.shared_inputs)
            provided_shared_inputs = inputs[primary_arity:]
            if to_json_value(provided_shared_inputs) != to_json_value(
                expected_shared_inputs
            ):
                raise ValueError("shared sample inputs cannot be edited")
            primary_inputs = inputs[:primary_arity]
        elif len(inputs) == primary_arity:
            primary_inputs = inputs
        else:
            raise ValueError(
                "inputs must contain either primary args only "
                f"({primary_arity}) or full invocation args ({total_arity})"
            )

        for value in primary_inputs:
            MemoryStore._validate_case_value(value)

        try:
            expected_output = expected_output_for_primary_inputs(
                template_key=match.puzzle.template_key,
                variables=match.puzzle.variables,
                primary_inputs=primary_inputs,
            )
        except ValueError:
            raise ValueError("sample inputs are invalid for this match") from None
        return TestCase(inputs=tuple(primary_inputs), output=expected_output)

    def _require_party(self, code: str) -> Party:
        party = self.parties.get(code)
        if party is None:
            raise ValueError("Party not found")
        return party

    def _require_match(self, match_id: str) -> Match:
        match = self.matches.get(match_id)
        if match is None:
            raise ValueError("Match not found")
        return match

    @staticmethod
    def _require_player(match: Match, user_id: str) -> MatchPlayer:
        player = match.players.get(user_id)
        if player is None:
            raise ValueError("User is not part of this match")
        return player


class SqliteStore(MemoryStore):
    def __init__(self, db_path: str) -> None:
        super().__init__()
        sqlite_path = Path(db_path).expanduser().resolve()
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        self._load_users()

    def create_user(
        self,
        *,
        name: str,
        guest: bool,
        elo: int = 1000,
        password_hash: str | None = None,
        normalized_name: str | None = None,
        profile_image_url: str | None = None,
        recent_ai_topics: list[str] | None = None,
    ) -> User:
        user = User(
            id=f"u_{uuid.uuid4().hex[:8]}",
            name=name.strip() or "Player",
            guest=guest,
            elo=elo,
            password_hash=password_hash,
            profile_image_url=profile_image_url,
            recent_ai_topics=list(recent_ai_topics or []),
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO users (
                    id,
                    name,
                    normalized_name,
                    guest,
                    elo,
                    password_hash,
                    profile_image_url,
                    recent_ai_topics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.name,
                    normalized_name,
                    1 if guest else 0,
                    user.elo,
                    user.password_hash,
                    user.profile_image_url,
                    json.dumps(user.recent_ai_topics, separators=(",", ":")),
                ),
            )

        self.users[user.id] = user
        if normalized_name is not None:
            self.user_name_index[normalized_name] = user.id
        return user

    def register_account(self, *, name: str, password: str) -> User:
        normalized_name = self._normalize_name(name)
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        try:
            return self.create_user(
                name=name,
                guest=False,
                elo=1000,
                password_hash=generate_password_hash(password),
                normalized_name=normalized_name,
            )
        except sqlite3.IntegrityError:
            raise ValueError("Display name is already registered") from None

    def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> User:
        user = super().change_password(
            user_id=user_id,
            current_password=current_password,
            new_password=new_password,
        )
        with self._conn:
            self._conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (user.password_hash, user.id),
            )
        return user

    def update_profile_image(
        self,
        *,
        user_id: str,
        profile_image_url: str | None,
    ) -> User:
        user = super().update_profile_image(
            user_id=user_id,
            profile_image_url=profile_image_url,
        )
        with self._conn:
            self._conn.execute(
                "UPDATE users SET profile_image_url = ? WHERE id = ?",
                (user.profile_image_url, user.id),
            )
        return user

    def admin_reset_all_elos(self, *, elo: int = 1000) -> int:
        updated = super().admin_reset_all_elos(elo=elo)
        with self._conn:
            self._conn.execute("UPDATE users SET elo = ?", (elo,))
        return updated

    def admin_set_user_elo(self, *, user_id: str, elo: int) -> User:
        user = super().admin_set_user_elo(user_id=user_id, elo=elo)
        with self._conn:
            self._conn.execute(
                "UPDATE users SET elo = ? WHERE id = ?",
                (user.elo, user.id),
            )
        return user

    def admin_delete_user(
        self, *, user_id: str
    ) -> tuple[User, list[Match], list[Party]]:
        deleted_user, cancelled_matches, updated_parties = super().admin_delete_user(
            user_id=user_id
        )
        with self._conn:
            self._conn.execute("DELETE FROM users WHERE id = ?", (deleted_user.id,))
        return deleted_user, cancelled_matches, updated_parties

    def finish_match(self, *, match_id: str) -> dict[str, int]:
        deltas = super().finish_match(match_id=match_id)
        if not deltas:
            return deltas

        with self._conn:
            self._conn.executemany(
                "UPDATE users SET elo = ? WHERE id = ?",
                [
                    (self.users[user_id].elo, user_id)
                    for user_id in deltas
                    if user_id in self.users
                ],
            )
        return deltas

    def _record_ai_topic_for_users(
        self, user_ids: list[str], *, topic_key: str
    ) -> None:
        super()._record_ai_topic_for_users(user_ids, topic_key=topic_key)
        if not user_ids:
            return

        updates: list[tuple[str, str]] = []
        for user_id in user_ids:
            user = self.users.get(user_id)
            if user is None:
                continue
            updates.append(
                (
                    json.dumps(user.recent_ai_topics, separators=(",", ":")),
                    user.id,
                )
            )
        if not updates:
            return

        with self._conn:
            self._conn.executemany(
                "UPDATE users SET recent_ai_topics_json = ? WHERE id = ?",
                updates,
            )

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT UNIQUE,
                    guest INTEGER NOT NULL CHECK (guest IN (0, 1)),
                    elo INTEGER NOT NULL,
                    password_hash TEXT,
                    profile_image_url TEXT,
                    recent_ai_topics_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )

            columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "profile_image_url" not in columns:
                try:
                    self._conn.execute(
                        "ALTER TABLE users ADD COLUMN profile_image_url TEXT"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).casefold():
                        raise

            if "recent_ai_topics_json" not in columns:
                try:
                    self._conn.execute(
                        "ALTER TABLE users "
                        "ADD COLUMN recent_ai_topics_json TEXT NOT NULL DEFAULT '[]'"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).casefold():
                        raise

    def _load_users(self) -> None:
        rows = self._conn.execute(
            """
            SELECT
                id,
                name,
                normalized_name,
                guest,
                elo,
                password_hash,
                profile_image_url,
                recent_ai_topics_json
            FROM users
            """
        ).fetchall()

        for row in rows:
            user = User(
                id=str(row["id"]),
                name=str(row["name"]),
                guest=bool(row["guest"]),
                elo=int(row["elo"]),
                password_hash=(
                    str(row["password_hash"])
                    if row["password_hash"] is not None
                    else None
                ),
                profile_image_url=(
                    str(row["profile_image_url"])
                    if row["profile_image_url"] is not None
                    else None
                ),
                recent_ai_topics=self._decode_recent_ai_topics(
                    row["recent_ai_topics_json"]
                ),
            )
            self.users[user.id] = user

            normalized_name = row["normalized_name"]
            if normalized_name is not None:
                self.user_name_index[str(normalized_name)] = user.id

    @staticmethod
    def _decode_recent_ai_topics(raw: object) -> list[str]:
        if not isinstance(raw, str) or not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        topics: list[str] = []
        for value in parsed:
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            if cleaned:
                topics.append(cleaned)
        return topics
