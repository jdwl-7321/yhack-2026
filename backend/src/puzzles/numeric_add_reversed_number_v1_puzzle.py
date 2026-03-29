from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_int_value,
)

template_key = "numeric-add-reversed-number-v1"
theme = "Numeric"
difficulties: tuple[Difficulty, ...] = ("hard",)
prompt = "Given a non-negative integer, return the sum of the integer and its digit-reversed form."
hint_level_1 = "Reverse digits in base-10 (for example, 120 becomes 21)."
hint_level_2 = "Compute the reversed number first, then add it to the original input."
hint_level_3 = "Return n + int(str(n)[::-1])."
contract = FunctionContract(parameter_types=("int",), return_type="int")


def add_number_and_reverse(value: int) -> int:
    if value < 0:
        raise ValueError("n must be non-negative")
    reversed_value = int(str(value)[::-1])
    return value + reversed_value


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, _difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    value = rng.randint(10, 99)
    return TestCase(inputs=(value,), output=add_number_and_reverse(value))


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
    value = require_int_value(primary_inputs[0], label="n")
    return add_number_and_reverse(value)
