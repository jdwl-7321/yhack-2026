import pytest

from constants import THEMES
from domain_types import Difficulty
from puzzle import (
    PuzzleInstance,
    format_value,
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


def test_generate_puzzle_is_seed_deterministic() -> None:
    first = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=99,
    )
    second = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=99,
    )

    assert first.variables == second.variables
    assert [case.inputs for case in first.hidden_tests] == [
        case.inputs for case in second.hidden_tests
    ]
    assert [case.output for case in first.hidden_tests] == [
        case.output for case in second.hidden_tests
    ]


def test_generate_puzzle_starts_with_three_samples() -> None:
    puzzle = generate_puzzle(theme="Algorithms", difficulty="easy", seed=77)
    assert len(puzzle.sample_tests) == 3


def test_hint_templates_render_human_readable_text() -> None:
    first = generate_puzzle(
        theme=THEMES[0],
        difficulty="easy",
        seed=123,
    )

    second = generate_puzzle(
        theme=THEMES[2],
        difficulty="easy",
        seed=456,
    )

    for puzzle in (first, second):
        assert puzzle.hint_level_1
        assert puzzle.hint_level_2
        assert puzzle.hint_level_3
        assert "{{" not in puzzle.hint_level_1
        assert "{{" not in puzzle.hint_level_2
        assert "{{" not in puzzle.hint_level_3


def test_two_sum_contract_uses_typed_parameters() -> None:
    puzzle = None
    for seed in range(1, 80):
        candidate = generate_puzzle(
            theme="Algorithms",
            difficulty="easy",
            seed=seed,
        )
        if candidate.template_key == "algorithms-index-pair-v2":
            puzzle = candidate
            break

    assert puzzle is not None
    assert puzzle.contract.parameter_types == ("list[int]", "int")
    assert puzzle.contract.return_type == "tuple[int, int]"


def test_format_value_packs_sequence_items_compactly() -> None:
    values = list(range(20))
    rendered = format_value(values)
    assert "[0, 1, 2" in rendered
    assert rendered.count("\n") < 10


@pytest.mark.parametrize(
    ("difficulty", "template_key"),
    [
        ("easy", "crypto-xor-byte-inference-v1"),
        ("medium", "crypto-shift-inference-v2"),
        ("hard", "crypto-substitution-inference-v2"),
        ("expert", "crypto-lsb-steganography-v1"),
    ],
)
def test_cryptography_templates_are_mapped_by_difficulty(
    difficulty: Difficulty, template_key: str
) -> None:
    puzzle = _crypto_puzzle_for_difficulty(difficulty)
    assert puzzle.template_key == template_key


def test_cryptography_contract_includes_examples_argument() -> None:
    puzzle = _crypto_puzzle_for_difficulty("hard")

    assert puzzle.contract.parameter_types == ("str", "list[list[str]]")
    assert puzzle.contract.return_type == "str"
    assert len(puzzle.shared_inputs) == 1

    examples = puzzle.shared_inputs[0]
    assert isinstance(examples, list)
    assert len(examples) == len(puzzle.sample_tests)

    for example, sample_case in zip(examples, puzzle.sample_tests, strict=True):
        assert example == [sample_case.inputs[0], sample_case.output]


def test_cryptography_scaffold_uses_samples_parameter_name() -> None:
    puzzle = _crypto_puzzle_for_difficulty("medium")
    scaffold = solution_scaffold(puzzle.contract)
    assert "def solution(text: str, samples: list[list[str]]) -> str:" in scaffold


def test_cryptography_xor_template_contract() -> None:
    puzzle = _crypto_puzzle_for_difficulty("easy")
    assert puzzle.contract.parameter_types == ("int", "list[list[int]]")
    assert puzzle.contract.return_type == "int"
    assert len(puzzle.shared_inputs) == 1


def test_cryptography_lsb_template_contract() -> None:
    puzzle = _crypto_puzzle_for_difficulty("expert")
    assert puzzle.contract.parameter_types == ("list[int]",)
    assert puzzle.contract.return_type == "str"

    numbers = puzzle.sample_tests[0].inputs[0]
    assert isinstance(numbers, list)
    assert len(numbers) % 8 == 0

    outputs = {case.output for case in puzzle.sample_tests}
    assert len(outputs) == len(puzzle.sample_tests)


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "expert"])
def test_algorithms_theme_covers_all_difficulties(difficulty: Difficulty) -> None:
    puzzle = generate_puzzle(theme="Algorithms", difficulty=difficulty, seed=53)
    assert puzzle.theme == "Algorithms"


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "expert"])
def test_numeric_theme_covers_all_difficulties(difficulty: Difficulty) -> None:
    puzzle = generate_puzzle(theme="Numeric", difficulty=difficulty, seed=91)
    assert puzzle.theme == "Numeric"


def test_requested_categories_exist_in_theme_catalog() -> None:
    expected = {"Cryptography", "Algorithms", "Numeric"}
    assert expected.issubset(set(THEMES))


def _crypto_puzzle_for_difficulty(difficulty: Difficulty) -> PuzzleInstance:
    return generate_puzzle(
        theme="Cryptography",
        difficulty=difficulty,
        seed=41,
    )
