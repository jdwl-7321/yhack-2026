from rating import (
    RankedResult,
    assign_ranked_difficulty,
    elo_deltas,
    order_ranked_results,
    ranked_matchmaking_window,
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


def test_ranked_matchmaking_window_expands_over_time() -> None:
    assert ranked_matchmaking_window(0) == 150
    assert ranked_matchmaking_window(14.9) == 150
    assert ranked_matchmaking_window(15.0) == 200
    assert ranked_matchmaking_window(120.0) == 550
    assert ranked_matchmaking_window(600.0) == 600


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


def test_forfeited_players_rank_below_non_forfeited() -> None:
    ranked = order_ranked_results(
        [
            RankedResult(
                "stayed",
                1000,
                solved_at=None,
                hidden_passed=0,
                best_score_at=15.0,
                forfeited=False,
            ),
            RankedResult(
                "quit",
                1000,
                solved_at=1.0,
                hidden_passed=10,
                best_score_at=1.0,
                forfeited=True,
            ),
        ]
    )

    assert [player.user_id for player in ranked] == ["stayed", "quit"]


def test_first_hint_has_no_positive_elo_penalty() -> None:
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
    first_hint = elo_deltas(
        [
            RankedResult(
                "winner",
                1000,
                solved_at=5.0,
                hidden_passed=6,
                best_score_at=5.0,
                hint_level=1,
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

    assert first_hint["winner"] == baseline["winner"]
    assert first_hint["loser"] == baseline["loser"]


def test_later_hints_reduce_positive_elo_gain() -> None:
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
