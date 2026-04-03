from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import random
import sqlite3
import string
from time import time
from typing import Callable, Literal, cast
import uuid
from werkzeug.security import check_password_hash, generate_password_hash

from constants import THEMES
from config import is_admin_username
from custom_puzzle import (
    CUSTOM_DIFFICULTY,
    CUSTOM_THEME,
    DEFAULT_CUSTOM_PUZZLE_SOURCE,
    build_custom_puzzle_instance,
    expected_output_for_custom_primary_inputs,
    slugify_title,
    validate_custom_puzzle_source,
)
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

PuzzleSelectionKind = Literal["catalog", "shared_puzzle", "shared_collection"]
CollectionRunMode = Literal["fixed", "random"]


def default_account_preferences() -> dict[str, object]:
    return {
        "appearanceMode": "light",
        "lightEditorTheme": "everforest-light",
        "darkEditorTheme": "catppuccin-mocha",
        "keybindMode": "normal",
        "customShortcuts": {
            "submit": "s",
            "test": "r",
            "hint": "h",
            "forfeit": "f",
        },
        "editorFontFamily": "roboto-mono",
        "editorFontSize": 14,
    }


def default_account_stats() -> dict[str, object]:
    return {
        "matchesStarted": 0,
        "matchesSolved": 0,
        "rankedFinished": 0,
        "rankedWins": 0,
        "hintsUsed": 0,
        "sampleRuns": 0,
        "submissions": 0,
        "forfeits": 0,
        "bestHiddenPassed": 0,
        "recentRuns": [],
        "recordedMatchIds": [],
    }


def _clone_json_object(value: dict[str, object]) -> dict[str, object]:
    return json.loads(json.dumps(value))


def _json_object_or_default(
    value: object,
    *,
    default_factory: Callable[[], dict[str, object]],
) -> dict[str, object]:
    if not isinstance(value, dict):
        return default_factory()
    return _clone_json_object(cast(dict[str, object], value))


def _json_object_from_db(
    value: object,
    *,
    default_factory: Callable[[], dict[str, object]],
) -> dict[str, object]:
    if value is None:
        return default_factory()
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return default_factory()
    return _json_object_or_default(decoded, default_factory=default_factory)


@dataclass(slots=True)
class User:
    id: str
    name: str
    guest: bool
    elo: int = 1000
    password_hash: str | None = None
    profile_image_url: str | None = None
    recent_ai_topics: list[str] = field(default_factory=list)
    account_preferences: dict[str, object] = field(
        default_factory=default_account_preferences
    )
    account_stats: dict[str, object] = field(default_factory=default_account_stats)


@dataclass(frozen=True, slots=True)
class CatalogPuzzleSelection:
    kind: Literal["catalog"]
    theme: str
    difficulty: Difficulty


@dataclass(frozen=True, slots=True)
class SharedPuzzleSelection:
    kind: Literal["shared_puzzle"]
    puzzle_id: str
    puzzle_slug: str
    owner_id: str


@dataclass(frozen=True, slots=True)
class SharedCollectionSelection:
    kind: Literal["shared_collection"]
    collection_id: str
    collection_slug: str
    owner_id: str
    run_mode: CollectionRunMode


PuzzleSelection = (
    CatalogPuzzleSelection | SharedPuzzleSelection | SharedCollectionSelection
)


@dataclass(slots=True)
class UserPuzzle:
    id: str
    owner_id: str
    title: str
    slug: str
    source_code: str
    created_at: float
    updated_at: float


@dataclass(slots=True)
class UserCollection:
    id: str
    owner_id: str
    title: str
    slug: str
    puzzle_ids: list[str]
    created_at: float
    updated_at: float


@dataclass(slots=True)
class CollectionRun:
    collection_id: str
    current_puzzle_id: str | None
    completed_puzzle_ids: list[str] = field(default_factory=list)
    skipped_puzzle_ids: list[str] = field(default_factory=list)
    remaining_puzzle_ids: list[str] = field(default_factory=list)
    run_mode: CollectionRunMode = "fixed"


@dataclass(slots=True)
class PartySettings:
    theme: str
    difficulty: Difficulty
    time_limit_seconds: int
    seed: int | None = None
    puzzle_selection: PuzzleSelection = field(
        default_factory=lambda: CatalogPuzzleSelection(
            kind="catalog",
            theme=THEMES[0],
            difficulty="easy",
        )
    )


@dataclass(slots=True)
class Party:
    code: str
    mode: Mode
    leader_id: str
    settings: PartySettings
    member_limit: int
    active_match_id: str | None = None
    members: list[str] = field(default_factory=list)
    collection_run: CollectionRun | None = None


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
    puzzle_source: dict[str, object] = field(default_factory=dict)
    custom_source_code: str | None = None
    custom_puzzle_id: str | None = None
    collection_id: str | None = None
    collection_puzzle_id: str | None = None
    skipped: bool = False


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
    _RANKED_ADMIN_TEMPLATE_KEY = "numeric-add-reversed-number-v1"

    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.user_name_index: dict[str, str] = {}
        self.user_puzzles: dict[str, UserPuzzle] = {}
        self.user_puzzle_slug_index: dict[str, str] = {}
        self.user_collections: dict[str, UserCollection] = {}
        self.user_collection_slug_index: dict[str, str] = {}
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
        account_preferences: dict[str, object] | None = None,
        account_stats: dict[str, object] | None = None,
    ) -> User:
        user = User(
            id=f"u_{uuid.uuid4().hex[:8]}",
            name=name.strip() or "Player",
            guest=guest,
            elo=elo,
            password_hash=password_hash,
            recent_ai_topics=list(recent_ai_topics or []),
            account_preferences=_json_object_or_default(
                account_preferences,
                default_factory=default_account_preferences,
            ),
            account_stats=_json_object_or_default(
                account_stats,
                default_factory=default_account_stats,
            ),
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

    def update_account_preferences(
        self,
        *,
        user_id: str,
        account_preferences: dict[str, object],
    ) -> User:
        user = self._require_user(user_id)
        user.account_preferences = _json_object_or_default(
            account_preferences,
            default_factory=default_account_preferences,
        )
        return user

    def update_account_stats(
        self,
        *,
        user_id: str,
        account_stats: dict[str, object],
    ) -> User:
        user = self._require_user(user_id)
        user.account_stats = _json_object_or_default(
            account_stats,
            default_factory=default_account_stats,
        )
        return user

    def list_user_puzzles(self, *, owner_id: str) -> list[UserPuzzle]:
        self._require_user(owner_id)
        return sorted(
            (
                puzzle
                for puzzle in self.user_puzzles.values()
                if puzzle.owner_id == owner_id
            ),
            key=lambda puzzle: (-puzzle.updated_at, puzzle.title.casefold(), puzzle.id),
        )

    def create_user_puzzle(
        self,
        *,
        owner_id: str,
        title: str,
        source_code: str | None = None,
    ) -> UserPuzzle:
        self._require_user_content_owner(owner_id)
        normalized_title = self._normalize_content_title(title, label="Puzzle title")
        resolved_source = (
            source_code if isinstance(source_code, str) and source_code.strip() else DEFAULT_CUSTOM_PUZZLE_SOURCE
        )
        validate_custom_puzzle_source(source_code=resolved_source)
        now = time()
        puzzle = UserPuzzle(
            id=f"up_{uuid.uuid4().hex[:10]}",
            owner_id=owner_id,
            title=normalized_title,
            slug=self._new_content_slug(normalized_title, existing=self.user_puzzle_slug_index),
            source_code=resolved_source,
            created_at=now,
            updated_at=now,
        )
        self.user_puzzles[puzzle.id] = puzzle
        self.user_puzzle_slug_index[puzzle.slug] = puzzle.id
        return puzzle

    def update_user_puzzle(
        self,
        *,
        owner_id: str,
        slug: str,
        title: str,
        source_code: str,
    ) -> UserPuzzle:
        self._require_user_content_owner(owner_id)
        puzzle = self.get_user_puzzle_by_slug(slug=slug)
        if puzzle.owner_id != owner_id:
            raise ValueError("Only the owner can edit this puzzle")
        normalized_title = self._normalize_content_title(title, label="Puzzle title")
        if not source_code.strip():
            raise ValueError("source_code is required")
        validate_custom_puzzle_source(source_code=source_code)
        puzzle.title = normalized_title
        puzzle.source_code = source_code
        puzzle.updated_at = time()
        return puzzle

    def get_user_puzzle_by_slug(self, *, slug: str) -> UserPuzzle:
        normalized_slug = self._normalize_slug_lookup(slug)
        puzzle_id = self.user_puzzle_slug_index.get(normalized_slug)
        if puzzle_id is None:
            raise ValueError("Puzzle not found")
        return self.user_puzzles[puzzle_id]

    def list_user_collections(self, *, owner_id: str) -> list[UserCollection]:
        self._require_user(owner_id)
        return sorted(
            (
                collection
                for collection in self.user_collections.values()
                if collection.owner_id == owner_id
            ),
            key=lambda collection: (
                -collection.updated_at,
                collection.title.casefold(),
                collection.id,
            ),
        )

    def create_user_collection(
        self,
        *,
        owner_id: str,
        title: str,
        puzzle_ids: list[str],
    ) -> UserCollection:
        self._require_user_content_owner(owner_id)
        normalized_title = self._normalize_content_title(
            title,
            label="Collection title",
        )
        resolved_puzzle_ids = self._validate_owned_collection_puzzles(
            owner_id=owner_id,
            puzzle_ids=puzzle_ids,
        )
        now = time()
        collection = UserCollection(
            id=f"uc_{uuid.uuid4().hex[:10]}",
            owner_id=owner_id,
            title=normalized_title,
            slug=self._new_content_slug(
                normalized_title,
                existing=self.user_collection_slug_index,
            ),
            puzzle_ids=resolved_puzzle_ids,
            created_at=now,
            updated_at=now,
        )
        self.user_collections[collection.id] = collection
        self.user_collection_slug_index[collection.slug] = collection.id
        return collection

    def update_user_collection(
        self,
        *,
        owner_id: str,
        slug: str,
        title: str,
        puzzle_ids: list[str],
    ) -> UserCollection:
        self._require_user_content_owner(owner_id)
        collection = self.get_user_collection_by_slug(slug=slug)
        if collection.owner_id != owner_id:
            raise ValueError("Only the owner can edit this collection")
        collection.title = self._normalize_content_title(title, label="Collection title")
        collection.puzzle_ids = self._validate_owned_collection_puzzles(
            owner_id=owner_id,
            puzzle_ids=puzzle_ids,
        )
        collection.updated_at = time()
        return collection

    def get_user_collection_by_slug(self, *, slug: str) -> UserCollection:
        normalized_slug = self._normalize_slug_lookup(slug)
        collection_id = self.user_collection_slug_index.get(normalized_slug)
        if collection_id is None:
            raise ValueError("Collection not found")
        return self.user_collections[collection_id]

    def create_party(
        self,
        *,
        leader_id: str,
        mode: Mode,
        theme: str,
        difficulty: Difficulty,
        time_limit_seconds: int,
        puzzle_selection: PuzzleSelection | None = None,
        member_limit: int | None = None,
        seed: int | None = None,
    ) -> Party:
        if leader_id not in self.users:
            raise ValueError("Leader user does not exist")
        resolved_selection = puzzle_selection or CatalogPuzzleSelection(
            kind="catalog",
            theme=theme,
            difficulty=difficulty,
        )
        selection_theme, selection_difficulty = self._selection_theme_and_difficulty(
            resolved_selection
        )
        self._validate_party_settings(
            puzzle_selection=resolved_selection,
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
                theme=selection_theme,
                difficulty=selection_difficulty,
                time_limit_seconds=time_limit_seconds,
                seed=seed,
                puzzle_selection=resolved_selection,
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
        puzzle_selection: PuzzleSelection | None = None,
        seed: int | None = None,
    ) -> Party:
        party = self._require_party(code)
        self._require_party_leader(party, leader_id)

        resolved_selection = puzzle_selection or CatalogPuzzleSelection(
            kind="catalog",
            theme=theme,
            difficulty=difficulty,
        )
        selection_theme, selection_difficulty = self._selection_theme_and_difficulty(
            resolved_selection
        )
        self._validate_party_settings(
            puzzle_selection=resolved_selection,
            time_limit_seconds=time_limit_seconds,
        )

        party.settings.theme = selection_theme
        party.settings.difficulty = selection_difficulty
        party.settings.time_limit_seconds = time_limit_seconds
        party.settings.seed = seed
        if party.settings.puzzle_selection != resolved_selection:
            party.collection_run = None
        party.settings.puzzle_selection = resolved_selection
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
                puzzle_selection=party.settings.puzzle_selection,
            ),
            member_limit=party.member_limit,
            active_match_id=None,
            members=list(party.members),
            collection_run=None,
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
        puzzle_selection: PuzzleSelection | None = None,
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
                or puzzle_selection is not None
            ):
                raise ValueError("Ranked matches do not support custom settings")
            ranked_template_override = self._ranked_template_override_for_members(
                members=members
            )
            avg_elo = sum(member.elo for member in members) / max(1, len(members))
            match_difficulty = assign_ranked_difficulty(avg_elo)
            match_theme = self._choose_next_ranked_theme(seed=seed)
            match_time_limit_seconds = 3600
        else:
            ranked_template_override = None
            match_time_limit_seconds = (
                time_limit_seconds
                if time_limit_seconds is not None
                else party.settings.time_limit_seconds
            )
            match_selection = self._selection_for_match_start(
                party=party,
                puzzle_selection=puzzle_selection,
                theme=theme,
                difficulty=difficulty,
            )
            self._validate_party_settings(
                puzzle_selection=match_selection,
                time_limit_seconds=match_time_limit_seconds,
            )
            match_theme, match_difficulty = self._selection_theme_and_difficulty(
                match_selection
            )
            party.settings.theme = match_theme
            party.settings.difficulty = match_difficulty
            party.settings.time_limit_seconds = match_time_limit_seconds
            if party.settings.puzzle_selection != match_selection:
                party.collection_run = None
            party.settings.puzzle_selection = match_selection

        match_seed = seed if seed is not None else random.randint(1, 10**9)
        puzzle_source: dict[str, object]
        custom_source_code: str | None = None
        custom_puzzle_id: str | None = None
        collection_id: str | None = None
        collection_puzzle_id: str | None = None
        if effective_mode == "ranked":
            puzzle = self._generate_match_puzzle(
                theme=match_theme,
                difficulty=match_difficulty,
                seed=match_seed,
                participant_user_ids=[member.id for member in members],
                forced_template_key=ranked_template_override,
            )
            puzzle_source = self.describe_catalog_source(
                theme=match_theme,
                difficulty=match_difficulty,
            )
        else:
            (
                puzzle,
                puzzle_source,
                custom_source_code,
                custom_puzzle_id,
                collection_id,
                collection_puzzle_id,
            ) = self._generate_party_match_content(
                party=party,
                selection=party.settings.puzzle_selection,
                seed=match_seed,
                participant_user_ids=[member.id for member in members],
            )
            match_theme = puzzle.theme
            match_difficulty = puzzle.difficulty
        if ranked_template_override is not None:
            match_theme = puzzle.theme
            match_difficulty = puzzle.difficulty
            puzzle_source = self.describe_catalog_source(
                theme=match_theme,
                difficulty=match_difficulty,
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
            puzzle_source=puzzle_source,
            custom_source_code=custom_source_code,
            custom_puzzle_id=custom_puzzle_id,
            collection_id=collection_id,
            collection_puzzle_id=collection_puzzle_id,
        )

        self.matches[match.id] = match
        party.active_match_id = match.id
        return match

    def skip_collection_match(
        self,
        *,
        match_id: str,
        leader_id: str,
        seed: int | None = None,
    ) -> tuple[Match, Match]:
        match = self._require_match(match_id)
        if match.mode not in {"casual", "zen"}:
            raise ValueError("Collection skip is only available in casual or zen matches")
        if match.finished or match.locked:
            raise ValueError("This match can no longer be skipped")
        if match.collection_id is None or match.collection_puzzle_id is None:
            raise ValueError("This match is not part of a collection run")

        party = self._require_party(match.party_code)
        self._require_party_leader(party, leader_id)
        run = party.collection_run
        if run is None or run.collection_id != match.collection_id:
            raise ValueError("This party has no active collection run")
        if run.current_puzzle_id != match.collection_puzzle_id:
            raise ValueError("Collection run state is out of sync")
        if not run.remaining_puzzle_ids:
            raise ValueError("No remaining puzzle exists in this collection run")

        next_puzzle_id = self._choose_next_collection_puzzle(
            run=run,
            seed=seed if seed is not None else party.settings.seed,
        )
        if next_puzzle_id is None:
            raise ValueError("No remaining puzzle exists in this collection run")

        run.skipped_puzzle_ids.append(match.collection_puzzle_id)
        run.current_puzzle_id = next_puzzle_id
        run.remaining_puzzle_ids = [
            puzzle_id for puzzle_id in run.remaining_puzzle_ids if puzzle_id != next_puzzle_id
        ]

        match.finished = True
        match.locked = True
        match.rating_deltas = {}
        match.skipped = True

        next_match = self.start_match(
            code=party.code,
            requester_id=leader_id,
            seed=seed,
        )
        return match, next_match

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
            self._mark_collection_match_completed(match)
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
        self._mark_collection_match_completed(match)
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
                "account_stats": _clone_json_object(user.account_stats),
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
        owned_puzzle_ids = [
            puzzle.id
            for puzzle in self.user_puzzles.values()
            if puzzle.owner_id == user_id
        ]
        owned_collection_ids = [
            collection.id
            for collection in self.user_collections.values()
            if collection.owner_id == user_id
        ]

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

            selection = party.settings.puzzle_selection
            should_reset_selection = False
            if selection.kind == "shared_puzzle" and cast(
                SharedPuzzleSelection, selection
            ).owner_id == user_id:
                should_reset_selection = True
            if selection.kind == "shared_collection" and cast(
                SharedCollectionSelection, selection
            ).owner_id == user_id:
                should_reset_selection = True
            if party.collection_run is not None and party.collection_run.collection_id in owned_collection_ids:
                party.collection_run = None
            if should_reset_selection:
                fallback_theme = (
                    party.settings.theme if party.settings.theme in THEMES else THEMES[0]
                )
                fallback_difficulty = (
                    party.settings.difficulty
                    if party.settings.difficulty in {"easy", "medium", "hard", "expert"}
                    else cast(Difficulty, "easy")
                )
                party.settings.puzzle_selection = CatalogPuzzleSelection(
                    kind="catalog",
                    theme=fallback_theme,
                    difficulty=fallback_difficulty,
                )
                party.settings.theme = fallback_theme
                party.settings.difficulty = fallback_difficulty

            updated_parties.append(party)

        for match in self.matches.values():
            if user_id not in match.players:
                continue
            match.players.pop(user_id, None)
            if match.rating_deltas is not None:
                match.rating_deltas.pop(user_id, None)

        self.ranked_queue.pop(user_id, None)
        self._delete_owned_custom_content(
            owner_id=user_id,
            owned_puzzle_ids=owned_puzzle_ids,
            owned_collection_ids=owned_collection_ids,
        )
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
        puzzle_selection: PuzzleSelection,
        time_limit_seconds: int,
    ) -> None:
        if time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be positive")
        if puzzle_selection.kind == "catalog":
            catalog = cast(CatalogPuzzleSelection, puzzle_selection)
            if catalog.theme not in THEMES:
                raise ValueError("Theme must be from the hardcoded catalog")
            if catalog.difficulty not in {"easy", "medium", "hard", "expert"}:
                raise ValueError("Invalid difficulty")
            return
        if puzzle_selection.kind == "shared_collection":
            collection = cast(SharedCollectionSelection, puzzle_selection)
            if collection.run_mode not in {"fixed", "random"}:
                raise ValueError("run_mode must be fixed or random")

    def _selection_for_match_start(
        self,
        *,
        party: Party,
        puzzle_selection: PuzzleSelection | None,
        theme: str | None,
        difficulty: Difficulty | None,
    ) -> PuzzleSelection:
        if puzzle_selection is not None:
            return puzzle_selection
        if theme is not None or difficulty is not None:
            return CatalogPuzzleSelection(
                kind="catalog",
                theme=theme if theme is not None else party.settings.theme,
                difficulty=(
                    difficulty if difficulty is not None else party.settings.difficulty
                ),
            )
        return party.settings.puzzle_selection

    @staticmethod
    def _selection_theme_and_difficulty(
        selection: PuzzleSelection,
    ) -> tuple[str, Difficulty]:
        if selection.kind == "catalog":
            catalog = cast(CatalogPuzzleSelection, selection)
            return catalog.theme, catalog.difficulty
        return CUSTOM_THEME, cast(Difficulty, CUSTOM_DIFFICULTY)

    def describe_catalog_source(
        self, *, theme: str, difficulty: Difficulty
    ) -> dict[str, object]:
        return {
            "kind": "catalog",
            "title": f"{theme} · {difficulty.upper()}",
            "theme": theme,
            "difficulty": difficulty,
            "slug": None,
            "owner_id": None,
            "owner_name": None,
            "share_path": None,
            "run_mode": None,
            "collection_progress": None,
            "current_puzzle_title": None,
            "current_puzzle_slug": None,
        }

    def describe_puzzle_source(
        self,
        *,
        selection: PuzzleSelection,
        collection_run: CollectionRun | None = None,
        current_puzzle_id: str | None = None,
    ) -> dict[str, object]:
        if selection.kind == "catalog":
            catalog = cast(CatalogPuzzleSelection, selection)
            return self.describe_catalog_source(
                theme=catalog.theme,
                difficulty=catalog.difficulty,
            )

        if selection.kind == "shared_puzzle":
            puzzle_selection = cast(SharedPuzzleSelection, selection)
            owner = self._require_user(puzzle_selection.owner_id)
            puzzle = self._require_user_puzzle(puzzle_selection.puzzle_id)
            return {
                "kind": puzzle_selection.kind,
                "title": puzzle.title,
                "theme": CUSTOM_THEME,
                "difficulty": CUSTOM_DIFFICULTY,
                "slug": puzzle.slug,
                "owner_id": owner.id,
                "owner_name": owner.name,
                "share_path": f"/puzzles/{puzzle.slug}",
                "run_mode": None,
                "collection_progress": None,
                "current_puzzle_title": None,
                "current_puzzle_slug": None,
            }

        collection_selection = cast(SharedCollectionSelection, selection)
        owner = self._require_user(collection_selection.owner_id)
        collection = self._require_user_collection(collection_selection.collection_id)
        progress = None
        current_title: str | None = None
        current_slug: str | None = None
        if current_puzzle_id is not None:
            current_puzzle = self._require_user_puzzle(current_puzzle_id)
            current_title = current_puzzle.title
            current_slug = current_puzzle.slug
        if collection_run is not None and collection_run.collection_id == collection.id:
            progress = {
                "completed_puzzle_ids": list(collection_run.completed_puzzle_ids),
                "skipped_puzzle_ids": list(collection_run.skipped_puzzle_ids),
                "remaining_puzzle_ids": list(collection_run.remaining_puzzle_ids),
                "current_puzzle_id": collection_run.current_puzzle_id,
                "total_puzzles": len(collection.puzzle_ids),
            }
        return {
            "kind": selection.kind,
            "title": collection.title,
            "theme": CUSTOM_THEME,
            "difficulty": CUSTOM_DIFFICULTY,
            "slug": collection.slug,
            "owner_id": owner.id,
            "owner_name": owner.name,
            "share_path": f"/collections/{collection.slug}",
            "run_mode": collection_selection.run_mode,
            "collection_progress": progress,
            "current_puzzle_title": current_title,
            "current_puzzle_slug": current_slug,
        }

    def _generate_party_match_content(
        self,
        *,
        party: Party,
        selection: PuzzleSelection,
        seed: int,
        participant_user_ids: list[str],
    ) -> tuple[
        PuzzleInstance,
        dict[str, object],
        str | None,
        str | None,
        str | None,
        str | None,
    ]:
        if selection.kind == "catalog":
            catalog = cast(CatalogPuzzleSelection, selection)
            puzzle = self._generate_match_puzzle(
                theme=catalog.theme,
                difficulty=catalog.difficulty,
                seed=seed,
                participant_user_ids=participant_user_ids,
            )
            return (
                puzzle,
                self.describe_puzzle_source(selection=selection),
                None,
                None,
                None,
                None,
            )

        if selection.kind == "shared_puzzle":
            puzzle_selection = cast(SharedPuzzleSelection, selection)
            puzzle_record = self._require_user_puzzle(puzzle_selection.puzzle_id)
            puzzle = build_custom_puzzle_instance(
                owner_id=puzzle_record.owner_id,
                puzzle_id=puzzle_record.id,
                source_code=puzzle_record.source_code,
                seed=seed,
            )
            return (
                puzzle,
                self.describe_puzzle_source(selection=selection),
                puzzle_record.source_code,
                puzzle_record.id,
                None,
                None,
            )

        collection_selection = cast(SharedCollectionSelection, selection)
        collection = self._require_user_collection(collection_selection.collection_id)
        run = self._ensure_collection_run(
            party=party,
            collection=collection,
            run_mode=collection_selection.run_mode,
            seed=seed,
        )
        current_puzzle_id = run.current_puzzle_id
        if current_puzzle_id is None:
            current_puzzle_id = self._choose_next_collection_puzzle(
                run=run,
                seed=seed,
            )
            if current_puzzle_id is None:
                raise ValueError("Collection run is complete")
            run.current_puzzle_id = current_puzzle_id
            run.remaining_puzzle_ids = [
                puzzle_id
                for puzzle_id in run.remaining_puzzle_ids
                if puzzle_id != current_puzzle_id
            ]

        puzzle_record = self._require_user_puzzle(current_puzzle_id)
        puzzle = build_custom_puzzle_instance(
            owner_id=puzzle_record.owner_id,
            puzzle_id=puzzle_record.id,
            source_code=puzzle_record.source_code,
            seed=seed,
        )
        return (
            puzzle,
            self.describe_puzzle_source(
                selection=collection_selection,
                collection_run=run,
                current_puzzle_id=current_puzzle_id,
            ),
            puzzle_record.source_code,
            puzzle_record.id,
            collection.id,
            current_puzzle_id,
        )

    def _ensure_collection_run(
        self,
        *,
        party: Party,
        collection: UserCollection,
        run_mode: CollectionRunMode,
        seed: int,
    ) -> CollectionRun:
        run = party.collection_run
        if run is not None and run.collection_id == collection.id and run.run_mode == run_mode:
            return run
        if not collection.puzzle_ids:
            raise ValueError("Collections must contain at least one puzzle")

        ordered_ids = list(collection.puzzle_ids)
        current_puzzle_id: str | None
        remaining_puzzle_ids: list[str]
        if run_mode == "fixed":
            current_puzzle_id = ordered_ids[0]
            remaining_puzzle_ids = ordered_ids[1:]
        else:
            chooser = random.Random(seed)
            current_puzzle_id = chooser.choice(ordered_ids)
            remaining_puzzle_ids = [
                puzzle_id for puzzle_id in ordered_ids if puzzle_id != current_puzzle_id
            ]

        run = CollectionRun(
            collection_id=collection.id,
            current_puzzle_id=current_puzzle_id,
            remaining_puzzle_ids=remaining_puzzle_ids,
            run_mode=run_mode,
        )
        party.collection_run = run
        return run

    def _choose_next_collection_puzzle(
        self,
        *,
        run: CollectionRun,
        seed: int | None,
    ) -> str | None:
        if not run.remaining_puzzle_ids:
            return None
        if run.run_mode == "fixed":
            return run.remaining_puzzle_ids[0]
        chooser = random.Random(seed)
        return chooser.choice(run.remaining_puzzle_ids)

    def _mark_collection_match_completed(self, match: Match) -> None:
        if (
            match.skipped
            or match.collection_id is None
            or match.collection_puzzle_id is None
            or not match.party_code
        ):
            return
        party = self.parties.get(match.party_code)
        if party is None or party.collection_run is None:
            return
        run = party.collection_run
        if run.collection_id != match.collection_id:
            return
        if match.collection_puzzle_id not in run.completed_puzzle_ids:
            run.completed_puzzle_ids.append(match.collection_puzzle_id)
        if run.current_puzzle_id == match.collection_puzzle_id:
            run.current_puzzle_id = None

    def _normalize_content_title(self, title: str, *, label: str) -> str:
        normalized = title.strip()
        if len(normalized) < 3:
            raise ValueError(f"{label} must be at least 3 characters")
        if len(normalized) > 80:
            raise ValueError(f"{label} must be 80 characters or less")
        return normalized

    @staticmethod
    def _normalize_slug_lookup(slug: str) -> str:
        normalized = slug.strip().casefold()
        if not normalized:
            raise ValueError("slug is required")
        return normalized

    def _new_content_slug(
        self, title: str, *, existing: dict[str, str]
    ) -> str:
        base = slugify_title(title)
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _validate_owned_collection_puzzles(
        self,
        *,
        owner_id: str,
        puzzle_ids: list[str],
    ) -> list[str]:
        if not isinstance(puzzle_ids, list):
            raise ValueError("puzzle_ids must be a list")
        if not puzzle_ids:
            raise ValueError("Collections must contain at least one puzzle")
        ordered: list[str] = []
        seen: set[str] = set()
        for puzzle_id in puzzle_ids:
            if not isinstance(puzzle_id, str) or not puzzle_id.strip():
                raise ValueError("puzzle_ids must contain puzzle ids")
            if puzzle_id in seen:
                raise ValueError("Collections cannot contain the same puzzle twice")
            puzzle = self._require_user_puzzle(puzzle_id)
            if puzzle.owner_id != owner_id:
                raise ValueError("Collections can only include your own puzzles")
            seen.add(puzzle_id)
            ordered.append(puzzle_id)
        return ordered

    def _require_user_content_owner(self, user_id: str) -> User:
        user = self._require_user(user_id)
        if user.guest:
            raise ValueError("Registered accounts are required for custom puzzles")
        if is_admin_username(user.name):
            raise ValueError("Admin accounts must use the admin puzzle system")
        return user

    def _generate_match_puzzle(
        self,
        *,
        theme: str,
        difficulty: Difficulty,
        seed: int,
        participant_user_ids: list[str] | None = None,
        forced_template_key: str | None = None,
    ) -> PuzzleInstance:
        if forced_template_key is not None:
            selected = next(
                (
                    template
                    for template in hardcoded_puzzle_templates()
                    if template.template_key == forced_template_key
                ),
                None,
            )
            if selected is None:
                raise ValueError("Forced puzzle template is not available")
        else:
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

        if selected.theme != "AI":
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

    def _ranked_template_override_for_members(
        self, *, members: list[User]
    ) -> str | None:
        if any(is_admin_username(member.name) for member in members):
            return self._RANKED_ADMIN_TEMPLATE_KEY
        return None

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
        ranked_template_override = self._ranked_template_override_for_members(
            members=members
        )
        avg_elo = sum(member.elo for member in members) / max(1, len(members))
        difficulty = assign_ranked_difficulty(avg_elo)
        theme = self._choose_next_ranked_theme(seed=seed)
        match_seed = seed if seed is not None else random.randint(1, 10**9)
        puzzle = self._generate_match_puzzle(
            theme=theme,
            difficulty=difficulty,
            seed=match_seed,
            participant_user_ids=[member.id for member in members],
            forced_template_key=ranked_template_override,
        )
        if ranked_template_override is not None:
            theme = puzzle.theme
            difficulty = puzzle.difficulty

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
            puzzle_source=self.describe_catalog_source(
                theme=theme,
                difficulty=difficulty,
            ),
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

    def _delete_owned_custom_content(
        self,
        *,
        owner_id: str,
        owned_puzzle_ids: list[str] | None = None,
        owned_collection_ids: list[str] | None = None,
    ) -> None:
        puzzle_ids = (
            owned_puzzle_ids
            if owned_puzzle_ids is not None
            else [
                puzzle.id
                for puzzle in self.user_puzzles.values()
                if puzzle.owner_id == owner_id
            ]
        )
        collection_ids = (
            owned_collection_ids
            if owned_collection_ids is not None
            else [
                collection.id
                for collection in self.user_collections.values()
                if collection.owner_id == owner_id
            ]
        )
        for collection_id in collection_ids:
            collection = self.user_collections.pop(collection_id, None)
            if collection is not None:
                self.user_collection_slug_index.pop(collection.slug, None)
        for puzzle_id in puzzle_ids:
            puzzle = self.user_puzzles.pop(puzzle_id, None)
            if puzzle is not None:
                self.user_puzzle_slug_index.pop(puzzle.slug, None)
        if not puzzle_ids:
            return
        removed_ids = set(puzzle_ids)
        for collection in self.user_collections.values():
            if any(puzzle_id in removed_ids for puzzle_id in collection.puzzle_ids):
                collection.puzzle_ids = [
                    puzzle_id
                    for puzzle_id in collection.puzzle_ids
                    if puzzle_id not in removed_ids
                ]

    def _require_user(self, user_id: str) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    def _require_user_puzzle(self, puzzle_id: str) -> UserPuzzle:
        puzzle = self.user_puzzles.get(puzzle_id)
        if puzzle is None:
            raise ValueError("Puzzle not found")
        return puzzle

    def _require_user_collection(self, collection_id: str) -> UserCollection:
        collection = self.user_collections.get(collection_id)
        if collection is None:
            raise ValueError("Collection not found")
        return collection

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
            if match.custom_source_code is None:
                expected_output = expected_output_for_primary_inputs(
                    template_key=match.puzzle.template_key,
                    variables=match.puzzle.variables,
                    primary_inputs=primary_inputs,
                )
            else:
                expected_output = expected_output_for_custom_primary_inputs(
                    source_code=match.custom_source_code,
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
        self._load_custom_content()

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
        account_preferences: dict[str, object] | None = None,
        account_stats: dict[str, object] | None = None,
    ) -> User:
        user = User(
            id=f"u_{uuid.uuid4().hex[:8]}",
            name=name.strip() or "Player",
            guest=guest,
            elo=elo,
            password_hash=password_hash,
            profile_image_url=profile_image_url,
            recent_ai_topics=list(recent_ai_topics or []),
            account_preferences=_json_object_or_default(
                account_preferences,
                default_factory=default_account_preferences,
            ),
            account_stats=_json_object_or_default(
                account_stats,
                default_factory=default_account_stats,
            ),
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
                    recent_ai_topics_json,
                    account_preferences_json,
                    account_stats_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(user.account_preferences),
                    json.dumps(user.account_stats),
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

    def update_account_preferences(
        self,
        *,
        user_id: str,
        account_preferences: dict[str, object],
    ) -> User:
        user = super().update_account_preferences(
            user_id=user_id,
            account_preferences=account_preferences,
        )
        with self._conn:
            self._conn.execute(
                "UPDATE users SET account_preferences_json = ? WHERE id = ?",
                (json.dumps(user.account_preferences), user.id),
            )
        return user

    def update_account_stats(
        self,
        *,
        user_id: str,
        account_stats: dict[str, object],
    ) -> User:
        user = super().update_account_stats(
            user_id=user_id,
            account_stats=account_stats,
        )
        with self._conn:
            self._conn.execute(
                "UPDATE users SET account_stats_json = ? WHERE id = ?",
                (json.dumps(user.account_stats), user.id),
            )
        return user

    def create_user_puzzle(
        self,
        *,
        owner_id: str,
        title: str,
        source_code: str | None = None,
    ) -> UserPuzzle:
        puzzle = super().create_user_puzzle(
            owner_id=owner_id,
            title=title,
            source_code=source_code,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO user_puzzles (
                    id,
                    owner_id,
                    title,
                    slug,
                    source_code,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    puzzle.id,
                    puzzle.owner_id,
                    puzzle.title,
                    puzzle.slug,
                    puzzle.source_code,
                    puzzle.created_at,
                    puzzle.updated_at,
                ),
            )
        return puzzle

    def update_user_puzzle(
        self,
        *,
        owner_id: str,
        slug: str,
        title: str,
        source_code: str,
    ) -> UserPuzzle:
        puzzle = super().update_user_puzzle(
            owner_id=owner_id,
            slug=slug,
            title=title,
            source_code=source_code,
        )
        with self._conn:
            self._conn.execute(
                """
                UPDATE user_puzzles
                SET title = ?, source_code = ?, updated_at = ?
                WHERE id = ?
                """,
                (puzzle.title, puzzle.source_code, puzzle.updated_at, puzzle.id),
            )
        return puzzle

    def create_user_collection(
        self,
        *,
        owner_id: str,
        title: str,
        puzzle_ids: list[str],
    ) -> UserCollection:
        collection = super().create_user_collection(
            owner_id=owner_id,
            title=title,
            puzzle_ids=puzzle_ids,
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO user_collections (
                    id,
                    owner_id,
                    title,
                    slug,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    collection.id,
                    collection.owner_id,
                    collection.title,
                    collection.slug,
                    collection.created_at,
                    collection.updated_at,
                ),
            )
            self._conn.executemany(
                """
                INSERT INTO user_collection_items (collection_id, position, puzzle_id)
                VALUES (?, ?, ?)
                """,
                [
                    (collection.id, position, puzzle_id)
                    for position, puzzle_id in enumerate(collection.puzzle_ids)
                ],
            )
        return collection

    def update_user_collection(
        self,
        *,
        owner_id: str,
        slug: str,
        title: str,
        puzzle_ids: list[str],
    ) -> UserCollection:
        collection = super().update_user_collection(
            owner_id=owner_id,
            slug=slug,
            title=title,
            puzzle_ids=puzzle_ids,
        )
        with self._conn:
            self._conn.execute(
                """
                UPDATE user_collections
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (collection.title, collection.updated_at, collection.id),
            )
            self._conn.execute(
                "DELETE FROM user_collection_items WHERE collection_id = ?",
                (collection.id,),
            )
            self._conn.executemany(
                """
                INSERT INTO user_collection_items (collection_id, position, puzzle_id)
                VALUES (?, ?, ?)
                """,
                [
                    (collection.id, position, puzzle_id)
                    for position, puzzle_id in enumerate(collection.puzzle_ids)
                ],
            )
        return collection

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
            self._conn.execute(
                "DELETE FROM user_collection_items WHERE puzzle_id IN (SELECT id FROM user_puzzles WHERE owner_id = ?)",
                (deleted_user.id,),
            )
            self._conn.execute(
                "DELETE FROM user_collection_items WHERE collection_id IN (SELECT id FROM user_collections WHERE owner_id = ?)",
                (deleted_user.id,),
            )
            self._conn.execute(
                "DELETE FROM user_collections WHERE owner_id = ?",
                (deleted_user.id,),
            )
            self._conn.execute(
                "DELETE FROM user_puzzles WHERE owner_id = ?",
                (deleted_user.id,),
            )
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
                    recent_ai_topics_json TEXT NOT NULL DEFAULT '[]',
                    account_preferences_json TEXT,
                    account_stats_json TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_puzzles (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    source_code TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_collections (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_collection_items (
                    collection_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    puzzle_id TEXT NOT NULL,
                    PRIMARY KEY (collection_id, position)
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
            if "account_preferences_json" not in columns:
                try:
                    self._conn.execute(
                        "ALTER TABLE users ADD COLUMN account_preferences_json TEXT"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).casefold():
                        raise
            if "account_stats_json" not in columns:
                try:
                    self._conn.execute(
                        "ALTER TABLE users ADD COLUMN account_stats_json TEXT"
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
                recent_ai_topics_json,
                account_preferences_json,
                account_stats_json
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
                account_preferences=_json_object_from_db(
                    row["account_preferences_json"],
                    default_factory=default_account_preferences,
                ),
                account_stats=_json_object_from_db(
                    row["account_stats_json"],
                    default_factory=default_account_stats,
                ),
            )
            self.users[user.id] = user

            normalized_name = row["normalized_name"]
            if normalized_name is not None:
                self.user_name_index[str(normalized_name)] = user.id

    def _load_custom_content(self) -> None:
        puzzle_rows = self._conn.execute(
            """
            SELECT id, owner_id, title, slug, source_code, created_at, updated_at
            FROM user_puzzles
            """
        ).fetchall()
        for row in puzzle_rows:
            puzzle = UserPuzzle(
                id=str(row["id"]),
                owner_id=str(row["owner_id"]),
                title=str(row["title"]),
                slug=str(row["slug"]),
                source_code=str(row["source_code"]),
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
            )
            self.user_puzzles[puzzle.id] = puzzle
            self.user_puzzle_slug_index[puzzle.slug] = puzzle.id

        collection_rows = self._conn.execute(
            """
            SELECT id, owner_id, title, slug, created_at, updated_at
            FROM user_collections
            """
        ).fetchall()
        items_by_collection: dict[str, list[str]] = {}
        item_rows = self._conn.execute(
            """
            SELECT collection_id, position, puzzle_id
            FROM user_collection_items
            ORDER BY collection_id, position
            """
        ).fetchall()
        for row in item_rows:
            collection_id = str(row["collection_id"])
            items_by_collection.setdefault(collection_id, []).append(str(row["puzzle_id"]))

        for row in collection_rows:
            collection = UserCollection(
                id=str(row["id"]),
                owner_id=str(row["owner_id"]),
                title=str(row["title"]),
                slug=str(row["slug"]),
                puzzle_ids=items_by_collection.get(str(row["id"]), []),
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
            )
            self.user_collections[collection.id] = collection
            self.user_collection_slug_index[collection.slug] = collection.id

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
