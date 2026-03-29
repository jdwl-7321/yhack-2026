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

template_key = "numeric-gcd-value-v1"
theme = "Numeric"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = (
    "Given two positive integers, return the largest integer that divides both inputs."
)
hint_level_1 = "The answer always divides both numbers exactly."
hint_level_2 = "The answer is as large as possible while still dividing both."
hint_level_3 = "Return gcd(a, b)."
contract = FunctionContract(parameter_types=("int", "int"), return_type="int")


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, _difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    left = rng.randint(2, 400)
    right = rng.randint(2, 400)
    return TestCase(inputs=(left, right), output=math.gcd(left, right))


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
    return math.gcd(left, right)
