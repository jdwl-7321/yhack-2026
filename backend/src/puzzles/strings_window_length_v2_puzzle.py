from __future__ import annotations

import random
import string
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_str_value,
)

template_key = "strings-window-length-v2"
theme = "Algorithms"
difficulties: tuple[Difficulty, ...] = ("hard",)
prompt = "Given a string, return the integer metric over contiguous segments that is suggested by the samples."
hint_level_1 = "Repeated characters force the active segment to shift forward."
hint_level_2 = "A sliding window with last-seen positions works efficiently."
hint_level_3 = (
    "Return the length of the longest substring with all distinct characters."
)
contract = FunctionContract(parameter_types=("str",), return_type="int")


def longest_unique_substring(text: str) -> int:
    last_index: dict[str, int] = {}
    best = 0
    start = 0
    for index, char in enumerate(text):
        if char in last_index and last_index[char] >= start:
            start = last_index[char] + 1
        last_index[char] = index
        best = max(best, index - start + 1)
    return best


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    length = {"easy": 10, "medium": 16, "hard": 24, "expert": 36}[difficulty]
    alphabet = {
        "easy": "abcde",
        "medium": "abcdefghi",
        "hard": "abcdefghijkl",
        "expert": string.ascii_lowercase,
    }[difficulty]
    text = "".join(rng.choice(alphabet) for _index in range(length))
    return TestCase(inputs=(text,), output=longest_unique_substring(text))


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
    text = require_str_value(primary_inputs[0], label="text")
    return longest_unique_substring(text)
