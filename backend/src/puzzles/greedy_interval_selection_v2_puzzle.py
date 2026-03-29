from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_intervals,
)

template_key = "greedy-interval-selection-v2"
theme = "Algorithms"
difficulties: tuple[Difficulty, ...] = ("medium",)
prompt = "Given integer intervals, return the maximum count selected under the non-overlap rule shown by samples."
hint_level_1 = "A selected interval blocks later intervals that start before it ends."
hint_level_2 = "Sorting by earliest finishing time enables the optimal strategy."
hint_level_3 = (
    "Choose the largest set of intervals where each next start is >= previous end."
)
contract = FunctionContract(
    parameter_types=("list[tuple[int, int]]",), return_type="int"
)


def max_non_overlapping(intervals: Sequence[tuple[int, int]]) -> int:
    ordered = sorted(intervals, key=lambda value: (value[1], value[0]))
    taken = 0
    current_end: int | None = None
    for start, end in ordered:
        if current_end is None or start >= current_end:
            taken += 1
            current_end = end
    return taken


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    count = {"easy": 6, "medium": 8, "hard": 11, "expert": 14}[difficulty]
    span = {"easy": 16, "medium": 30, "hard": 45, "expert": 70}[difficulty]
    width = {"easy": 5, "medium": 8, "hard": 12, "expert": 18}[difficulty]
    intervals = [
        (start, start + rng.randint(1, width))
        for start in (rng.randint(0, span) for _index in range(count))
    ]
    rng.shuffle(intervals)
    return TestCase(inputs=(intervals,), output=max_non_overlapping(intervals))


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
    intervals = require_intervals(primary_inputs[0])
    return max_non_overlapping(intervals)
