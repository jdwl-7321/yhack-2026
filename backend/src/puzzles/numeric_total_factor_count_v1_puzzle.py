from __future__ import annotations

import math
import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_int_sequence,
)

template_key = "numeric-total-factor-count-v1"
theme = "Numeric"
difficulties: tuple[Difficulty, ...] = ("expert",)
prompt = "Given a list of positive integers, return the total number of positive factors across all numbers in the list."
hint_level_1 = "Each integer contributes the count of its own positive divisors."
hint_level_2 = "Compute divisor counts per value, then sum them."
hint_level_3 = "Return sum(d(n) for n in values), where d(n) is the divisor count."
contract = FunctionContract(parameter_types=("list[int]",), return_type="int")


def factor_count(value: int) -> int:
    normalized = abs(value)
    if normalized <= 1:
        return 1

    total = 0
    limit = int(math.isqrt(normalized))
    for candidate in range(1, limit + 1):
        if normalized % candidate != 0:
            continue
        partner = normalized // candidate
        total += 1 if partner == candidate else 2
    return total


def total_factor_count(values: Sequence[int]) -> int:
    return sum(factor_count(value) for value in values)


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, _difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    length = 6
    values = [rng.randint(2, 6000) for _index in range(length)]
    return TestCase(inputs=(values,), output=total_factor_count(values))


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
    values = require_int_sequence(primary_inputs[0], label="values")
    return total_factor_count(values)
