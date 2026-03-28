from __future__ import annotations

from dataclasses import dataclass, field
import random
import string
from time import time
import uuid
from werkzeug.security import check_password_hash, generate_password_hash

from constants import THEMES
from judge import JudgeResult, judge_submission
from puzzle import (
    NoveltyPool,
    PuzzleInstance,
    TestCase,
    generate_additional_hidden_test,
    generate_puzzle,
)
from rating import (
    RankedResult,
    assign_ranked_difficulty,
    elo_deltas,
    order_ranked_results,
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


class MemoryStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.user_name_index: dict[str, str] = {}
        self.parties: dict[str, Party] = {}
        self.matches: dict[str, Match] = {}
        self.novelty_pool = NoveltyPool()

    def create_user(
        self,
        *,
        name: str,
        guest: bool,
        elo: int = 1000,
        password_hash: str | None = None,
    ) -> User:
        user = User(
            id=f"u_{uuid.uuid4().hex[:8]}",
            name=name.strip() or "Player",
            guest=guest,
            elo=elo,
            password_hash=password_hash,
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

    def create_party(
        self,
        *,
        leader_id: str,
        mode: Mode,
        theme: str,
        difficulty: Difficulty,
        time_limit_seconds: int,
        seed: int | None = None,
    ) -> Party:
        if leader_id not in self.users:
            raise ValueError("Leader user does not exist")
        if theme not in THEMES:
            raise ValueError("Theme must be from the hardcoded catalog")
        if difficulty not in {"easy", "medium", "hard", "expert"}:
            raise ValueError("Invalid difficulty")
        if time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be positive")

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
            members=[leader_id],
        )
        self.parties[party.code] = party
        return party

    def join_party(self, *, code: str, user_id: str) -> Party:
        party = self._require_party(code)
        if user_id not in self.users:
            raise ValueError("User does not exist")
        if user_id not in party.members:
            party.members.append(user_id)
        return party

    def start_match(self, *, code: str, seed: int | None = None) -> Match:
        party = self._require_party(code)
        members = [self._require_user(user_id) for user_id in party.members]

        effective_mode = resolve_mode(
            party.mode,
            has_guest=any(member.guest for member in members),
        )

        if effective_mode == "ranked":
            avg_elo = sum(member.elo for member in members) / max(1, len(members))
            difficulty = assign_ranked_difficulty(avg_elo)
            chooser = random.Random(seed) if seed is not None else random
            theme = chooser.choice(THEMES)
            time_limit_seconds = 3600
        else:
            difficulty = party.settings.difficulty
            theme = party.settings.theme
            time_limit_seconds = party.settings.time_limit_seconds

        match_seed = seed if seed is not None else random.randint(1, 10**9)
        puzzle = generate_puzzle(
            theme=theme,
            difficulty=difficulty,
            seed=match_seed,
            novelty_pool=self.novelty_pool,
        )

        match = Match(
            id=f"m_{uuid.uuid4().hex[:10]}",
            party_code=code,
            mode=effective_mode,
            theme=theme,
            difficulty=difficulty,
            time_limit_seconds=time_limit_seconds,
            puzzle=puzzle,
            created_at=time(),
            players={user.id: MatchPlayer(user_id=user.id) for user in members},
        )

        self.matches[match.id] = match
        return match

    def get_match(self, *, match_id: str) -> Match:
        return self._require_match(match_id)

    def submit(self, *, match_id: str, user_id: str, code: str) -> JudgeResult:
        match = self._require_match(match_id)
        player = self._require_player(match, user_id)
        if player.forfeited:
            raise ValueError("Player already forfeited")

        result = judge_submission(
            code=code,
            sample_tests=match.puzzle.sample_tests,
            hidden_tests=match.puzzle.hidden_tests,
        )

        if result.first_failed_hidden_test is None:
            player.last_failed_hidden_test = None
        else:
            player.last_failed_hidden_test = TestCase(
                input_str=result.first_failed_hidden_test.input_str,
                output_str=result.first_failed_hidden_test.expected_output,
            )

        now = time()
        if result.hidden_passed >= player.hidden_passed:
            player.hidden_passed = result.hidden_passed
            player.best_score_at = now
        if result.verdict == "accepted" and player.solved_at is None:
            player.solved_at = now

        match.submissions.append(result)
        return result

    def test_samples(self, *, match_id: str, user_id: str, code: str) -> JudgeResult:
        match = self._require_match(match_id)
        player = self._require_player(match, user_id)
        if player.forfeited:
            raise ValueError("Player already forfeited")

        return judge_submission(
            code=code,
            sample_tests=match.puzzle.sample_tests,
            hidden_tests=match.puzzle.hidden_tests,
            include_hidden_tests=False,
        )

    def promote_failed_hidden_test(
        self, *, match_id: str, user_id: str
    ) -> list[TestCase]:
        match = self._require_match(match_id)
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
            )
            match.puzzle.hidden_tests.append(replacement)

        player.last_failed_hidden_test = None
        return match.puzzle.sample_tests

    def request_hint(self, *, match_id: str, user_id: str, level: int) -> str:
        if level not in {1, 2}:
            raise ValueError("Hint level must be 1 or 2")

        match = self._require_match(match_id)
        player = self._require_player(match, user_id)
        if level in player.hints_used:
            raise ValueError("Hint level already used")

        player.hints_used.add(level)
        player.hint_level = max(player.hint_level, level)
        return match.puzzle.hint_level_1 if level == 1 else match.puzzle.hint_level_2

    def forfeit(self, *, match_id: str, user_id: str) -> None:
        match = self._require_match(match_id)
        player = self._require_player(match, user_id)
        player.forfeited = True

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
                )
            )

        deltas = elo_deltas(ranking_input, match.difficulty)
        for user_id, delta in deltas.items():
            self.users[user_id].elo += delta

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

    def _new_party_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choice(alphabet) for _ in range(6))
            if code not in self.parties:
                return code

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip()
        if len(normalized) < 3:
            raise ValueError("Display name must be at least 3 characters")
        if len(normalized) > 24:
            raise ValueError("Display name must be 24 characters or less")
        return normalized.casefold()

    def _require_user(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

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
