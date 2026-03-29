import pytest

from constants import THEMES
from puzzle import (
    NoveltyPool,
    PuzzleInstance,
    generate_puzzle,
    parse_variable_specs,
    sample_parameters,
    solution_scaffold,
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
    assert [case.inputs for case in first.hidden_tests] == [
        case.inputs for case in second.hidden_tests
    ]
    assert [case.output for case in first.hidden_tests] == [
        case.output for case in second.hidden_tests
    ]


def test_hint_templates_render_human_readable_text() -> None:
    first = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=123,
        novelty_pool=NoveltyPool(similarity_threshold=1.1),
    )

    second = generate_puzzle(
        theme=THEMES[2],
        difficulty="easy",
        seed=456,
        novelty_pool=NoveltyPool(similarity_threshold=1.1),
    )

    for puzzle in (first, second):
        assert puzzle.hint_level_1
        assert puzzle.hint_level_2
        assert puzzle.hint_level_3
        assert "{{" not in puzzle.hint_level_1
        assert "{{" not in puzzle.hint_level_2
        assert "{{" not in puzzle.hint_level_3


def test_two_sum_contract_uses_typed_parameters() -> None:
    puzzle = generate_puzzle(
        theme="Algorithms",
        difficulty="easy",
        seed=321,
        novelty_pool=NoveltyPool(similarity_threshold=1.1),
    )

    assert puzzle.contract.parameter_types == ("list[int]", "int")
    assert puzzle.contract.return_type == "tuple[int, int]"


def test_cryptography_contract_includes_examples_argument() -> None:
    puzzle = _pick_crypto_template(
        {
            "crypto-shift-inference-v2",
            "crypto-substitution-inference-v2",
        }
    )

    assert puzzle.contract.parameter_types == ("str", "list[list[str]]")
    assert puzzle.contract.return_type == "str"
    assert len(puzzle.shared_inputs) == 1

    examples = puzzle.shared_inputs[0]
    assert isinstance(examples, list)
    assert len(examples) == len(puzzle.sample_tests)

    for example, sample_case in zip(examples, puzzle.sample_tests, strict=True):
        assert example == [sample_case.inputs[0], sample_case.output]


def test_cryptography_scaffold_uses_samples_parameter_name() -> None:
    puzzle = _pick_crypto_template(
        {
            "crypto-shift-inference-v2",
            "crypto-substitution-inference-v2",
        }
    )
    scaffold = solution_scaffold(puzzle.contract)
    assert "def solution(text: str, samples: list[list[str]]) -> str:" in scaffold


def test_cryptography_lsb_template_contract() -> None:
    puzzle = _pick_crypto_template({"crypto-lsb-steganography-v1"})
    assert puzzle.contract.parameter_types == ("list[int]",)
    assert puzzle.contract.return_type == "str"

    numbers = puzzle.sample_tests[0].inputs[0]
    assert isinstance(numbers, list)
    assert len(numbers) % 8 == 0


def test_requested_categories_exist_in_theme_catalog() -> None:
    expected = {"Cryptography", "Algorithms", "Search", "Numeric"}
    assert expected.issubset(set(THEMES))


def _pick_crypto_template(expected_keys: set[str]) -> PuzzleInstance:
    for seed in range(1, 300):
        puzzle = generate_puzzle(
            theme="Cryptography",
            difficulty="easy",
            seed=seed,
            novelty_pool=NoveltyPool(similarity_threshold=1.1),
        )
        if puzzle.template_key in expected_keys:
            return puzzle
    raise AssertionError(f"Failed to generate crypto template from {expected_keys}")
