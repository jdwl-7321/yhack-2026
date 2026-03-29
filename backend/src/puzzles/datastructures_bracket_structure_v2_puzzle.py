from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_str_value,
)

template_key = "datastructures-bracket-structure-v2"
theme = "Algorithms"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = "Given a bracket string, return a boolean according to the structural validity rule implied by samples."
hint_level_1 = "Track opening symbols and how they are closed."
hint_level_2 = "A closing bracket must match the most recent unmatched opening bracket."
hint_level_3 = "Return True only when every bracket is matched and correctly nested."
contract = FunctionContract(parameter_types=("str",), return_type="bool")

BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}


def is_balanced_brackets(source: str) -> bool:
    stack: list[str] = []
    for char in source:
        if char in BRACKET_PAIRS:
            stack.append(char)
            continue
        if char in ")]}":
            if not stack:
                return False
            opener = stack.pop()
            if BRACKET_PAIRS[opener] != char:
                return False
    return not stack


def make_valid_bracket_text(rng: random.Random, pair_count: int) -> str:
    stack: list[str] = []
    chars: list[str] = []
    while len(chars) < pair_count * 2:
        can_open_more = len(chars) + len(stack) < pair_count * 2
        if can_open_more and (not stack or rng.random() < 0.62):
            opener = rng.choice(list(BRACKET_PAIRS))
            stack.append(opener)
            chars.append(opener)
        else:
            opener = stack.pop()
            chars.append(BRACKET_PAIRS[opener])
    return "".join(chars)


def make_invalid_bracket_text(rng: random.Random, pair_count: int) -> str:
    for _attempt in range(32):
        baseline = list(make_valid_bracket_text(rng, pair_count))
        mode = rng.choice(["swap", "drop", "append"])
        if mode == "swap" and baseline:
            index = rng.randrange(len(baseline))
            baseline[index] = rng.choice(list("()[]{}"))
        elif mode == "drop" and len(baseline) > 1:
            del baseline[rng.randrange(len(baseline))]
        else:
            baseline.append(rng.choice(list(BRACKET_PAIRS)))

        candidate = "".join(baseline)
        if not is_balanced_brackets(candidate):
            return candidate

    return "(" * pair_count


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    pair_count = {"easy": 4, "medium": 6, "hard": 8, "expert": 11}[difficulty]
    if rng.random() < 0.5:
        text = make_valid_bracket_text(rng, pair_count)
    else:
        text = make_invalid_bracket_text(rng, pair_count)
    return TestCase(inputs=(text,), output=is_balanced_brackets(text))


def shared_input_factory(
    params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return no_shared_inputs(params, sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    del variables
    require_arity(primary_inputs, expected=1)
    text = require_str_value(primary_inputs[0], label="source")
    return is_balanced_brackets(text)
