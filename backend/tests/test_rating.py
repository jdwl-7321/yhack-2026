from rating import (
    RankedResult,
    assign_ranked_difficulty,
    elo_deltas,
    order_ranked_results,
    resolve_mode,
)


def test_ranked_difficulty_buckets() -> None:
    assert assign_ranked_difficulty(899) == "easy"
    assert assign_ranked_difficulty(900) == "medium"
    assert assign_ranked_difficulty(1099) == "medium"
    assert assign_ranked_difficulty(1100) == "hard"
    assert assign_ranked_difficulty(1299) == "hard"
    assert assign_ranked_difficulty(1300) == "expert"


def test_ranked_mode_falls_back_for_guests() -> None:
    assert resolve_mode("ranked", has_guest=True) == "casual"
    assert resolve_mode("ranked", has_guest=False) == "ranked"


def test_rank_order_tie_breaking() -> None:
    ranked = order_ranked_results(
        [
            RankedResult(
                "late", 1000, solved_at=20.0, hidden_passed=0, best_score_at=20.0
            ),
            RankedResult(
                "early", 1000, solved_at=10.0, hidden_passed=0, best_score_at=10.0
            ),
            RankedResult(
                "unsolved_high",
                1000,
                solved_at=None,
                hidden_passed=5,
                best_score_at=30.0,
            ),
            RankedResult(
                "unsolved_low",
                1000,
                solved_at=None,
                hidden_passed=1,
                best_score_at=5.0,
            ),
        ]
    )

    assert [player.user_id for player in ranked] == [
        "early",
        "late",
        "unsolved_high",
        "unsolved_low",
    ]


def test_hint_level_reduces_positive_elo_gain() -> None:
    baseline = elo_deltas(
        [
            RankedResult(
                "winner",
                1000,
                solved_at=5.0,
                hidden_passed=6,
                best_score_at=5.0,
                hint_level=0,
            ),
            RankedResult(
                "loser",
                1000,
                solved_at=None,
                hidden_passed=0,
                best_score_at=50.0,
                hint_level=0,
            ),
        ],
        difficulty="medium",
    )
    penalized = elo_deltas(
        [
            RankedResult(
                "winner",
                1000,
                solved_at=5.0,
                hidden_passed=6,
                best_score_at=5.0,
                hint_level=2,
            ),
            RankedResult(
                "loser",
                1000,
                solved_at=None,
                hidden_passed=0,
                best_score_at=50.0,
                hint_level=0,
            ),
        ],
        difficulty="medium",
    )

    assert penalized["winner"] < baseline["winner"]
    assert penalized["loser"] == baseline["loser"]
