from __future__ import annotations

from dataclasses import dataclass

from domain_types import Difficulty, Mode

_DIFFICULTY_MULTIPLIER = {
    "easy": 0.9,
    "medium": 1.0,
    "hard": 1.1,
    "expert": 1.2,
}

_HINT_GAIN_MULTIPLIER = {
    0: 1.0,
    1: 1.0,
    2: 0.85,
    3: 0.7,
}


@dataclass(frozen=True, slots=True)
class RankedResult:
    user_id: str
    elo: int
    solved_at: float | None
    hidden_passed: int
    best_score_at: float
    hint_level: int = 0


def resolve_mode(requested_mode: Mode, has_guest: bool) -> Mode:
    if requested_mode == "ranked" and has_guest:
        return "casual"
    return requested_mode


def assign_ranked_difficulty(avg_elo: float) -> Difficulty:
    if avg_elo < 900:
        return "easy"
    if avg_elo < 1100:
        return "medium"
    if avg_elo < 1300:
        return "hard"
    return "expert"


def order_ranked_results(results: list[RankedResult]) -> list[RankedResult]:
    def key(item: RankedResult) -> tuple[int, float, int, float]:
        if item.solved_at is not None:
            return (0, item.solved_at, 0, 0.0)
        return (1, 0.0, -item.hidden_passed, item.best_score_at)

    return sorted(results, key=key)


def elo_deltas(results: list[RankedResult], difficulty: Difficulty) -> dict[str, int]:
    if not results:
        return {}

    ranked = order_ranked_results(results)
    player_count = len(ranked)
    total_elo = sum(player.elo for player in ranked)
    base_k = 24.0 * _DIFFICULTY_MULTIPLIER[difficulty]
    deltas: dict[str, int] = {}

    for placement, player in enumerate(ranked):
        if player_count == 1:
            actual = 1.0
            field_avg = float(player.elo)
        else:
            actual = 1.0 - (placement / (player_count - 1))
            field_avg = (total_elo - player.elo) / (player_count - 1)

        expected = 1.0 / (1.0 + 10.0 ** ((field_avg - player.elo) / 400.0))
        raw_delta = round(base_k * (actual - expected))

        if raw_delta > 0:
            hint_level = min(3, max(0, player.hint_level))
            raw_delta = round(raw_delta * _HINT_GAIN_MULTIPLIER[hint_level])

        deltas[player.user_id] = max(-64, min(64, raw_delta))

    return deltas
