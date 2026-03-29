from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_int_sequence,
    require_int_value,
)

template_key = "algorithms-index-pair-v2"
theme = "Algorithms"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = (
    "Given a list of integers and a target integer, return a pair of indices that follows "
    "the hidden rule shown by the samples."
)
hint_level_1 = (
    "The output always has two indices where the first is smaller than the second."
)
hint_level_2 = "Exactly one valid pair exists per case."
hint_level_3 = "Return indices i, j such that values[i] + values[j] == target."
contract = FunctionContract(
    parameter_types=("list[int]", "int"),
    return_type="tuple[int, int]",
)


def two_sum_pairs(values: Sequence[int], target: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            if values[left] + values[right] == target:
                pairs.append((left, right))
    return pairs


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    length = {"easy": 6, "medium": 8, "hard": 11, "expert": 14}[difficulty]
    span = {"easy": 20, "medium": 60, "hard": 130, "expert": 260}[difficulty]
    for _attempt in range(300):
        values = [rng.randint(-span, span) for _index in range(length)]
        first, second = sorted(rng.sample(range(length), 2))
        target = values[first] + values[second]
        pairs = two_sum_pairs(values, target)
        if len(pairs) == 1:
            return TestCase(inputs=(values, target), output=pairs[0])
    raise ValueError("Unable to construct unique index-pair case")


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
    require_arity(primary_inputs, expected=2)
    values = require_int_sequence(primary_inputs[0], label="values")
    target = require_int_value(primary_inputs[1], label="target")
    pairs = two_sum_pairs(values, target)
    if len(pairs) != 1:
        raise ValueError("two-sum samples must contain exactly one valid index pair")
    return pairs[0]
