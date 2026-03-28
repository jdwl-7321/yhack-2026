import pytest

from constants import THEMES
from puzzle import (
    NoveltyPool,
    generate_puzzle,
    parse_variable_specs,
    sample_parameters,
)


def test_variable_schema_and_deterministic_sampling() -> None:
    specs = parse_variable_specs(
        [
            {
                "name": "n",
                "type": "int",
                "sampling": "uniform",
                "range": {"min": 2, "max": 20, "inclusive": True},
            },
            {
                "name": "kind",
                "type": "choice",
                "sampling": "fixed_list",
                "range": {"values": ["a", "b", "c"]},
            },
        ]
    )

    first = sample_parameters(specs, seed=1234)
    second = sample_parameters(specs, seed=1234)
    assert first == second


def test_invalid_variable_schema_rejected() -> None:
    with pytest.raises(ValueError):
        parse_variable_specs(
            [
                {
                    "name": "bad",
                    "type": "int",
                    "sampling": "uniform",
                    "range": {"min": 10, "max": 2, "inclusive": True},
                }
            ]
        )


def test_novelty_pool_evicts_when_over_50() -> None:
    pool = NoveltyPool(size=50, similarity_threshold=1.1)
    for index in range(51):
        assert pool.accept(f"fp-{index}", f"sig-{index}")

    assert len(pool) == 50
    assert pool.accept("fp-0", "sig-0")


def test_generate_puzzle_is_seed_deterministic() -> None:
    first = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=99,
        novelty_pool=NoveltyPool(similarity_threshold=1.1),
    )
    second = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=99,
        novelty_pool=NoveltyPool(similarity_threshold=1.1),
    )

    assert first.variables == second.variables
    assert [case.input_str for case in first.hidden_tests] == [
        case.input_str for case in second.hidden_tests
    ]
    assert [case.output_str for case in first.hidden_tests] == [
        case.output_str for case in second.hidden_tests
    ]
