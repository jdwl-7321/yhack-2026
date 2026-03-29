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
    require_int_value,
)

template_key = "numeric-lcm-value-v1"
theme = "Numeric"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = "Given two positive integers, return the smallest positive integer that is a multiple of both."
hint_level_1 = "The result must be divisible by both inputs."
hint_level_2 = "The result is the minimum positive shared multiple."
hint_level_3 = "Return lcm(a, b)."
contract = FunctionContract(parameter_types=("int", "int"), return_type="int")


def lcm(left: int, right: int) -> int:
    gcd_value = math.gcd(left, right)
    return abs(left * right) // gcd_value


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, _difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    left = rng.randint(2, 90)
    right = rng.randint(2, 90)
    return TestCase(inputs=(left, right), output=lcm(left, right))


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
    left = require_int_value(primary_inputs[0], label="a")
    right = require_int_value(primary_inputs[1], label="b")
    return lcm(left, right)
