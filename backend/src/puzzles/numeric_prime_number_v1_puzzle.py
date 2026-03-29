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

template_key = "numeric-prime-number-v1"
theme = "Numeric"
difficulties: tuple[Difficulty, ...] = ("medium",)
prompt = "Given an integer, return whether it is prime."
hint_level_1 = "Prime numbers are integers greater than 1."
hint_level_2 = "A prime has exactly two positive divisors: 1 and itself."
hint_level_3 = "Return True iff n has no divisor in 2..sqrt(n)."
contract = FunctionContract(parameter_types=("int",), return_type="bool")


def is_prime(value: int) -> bool:
    if value < 2:
        return False
    if value == 2:
        return True
    if value % 2 == 0:
        return False
    limit = int(math.isqrt(value))
    for candidate in range(3, limit + 1, 2):
        if value % candidate == 0:
            return False
    return True


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, _difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    value = rng.randint(2, 5000)
    return TestCase(inputs=(value,), output=is_prime(value))


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
    return is_prime(value)
