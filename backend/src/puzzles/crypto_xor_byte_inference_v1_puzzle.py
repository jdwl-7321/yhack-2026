from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    require_arity,
    require_int_value,
    require_variable_int,
    sample_pairs_shared_scalar_inputs,
)

template_key = "crypto-xor-byte-inference-v1"
theme = "Cryptography"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = (
    "A deterministic 8-bit XOR mask is used across this match. "
    "`examples` contains visible [input, output] byte pairs produced with that same mask. "
    "Implement solution(value, examples) so it applies the same transformation to `value`."
)
hint_level_1 = "Every value is an integer byte in the inclusive range 0..255."
hint_level_2 = "A single hidden mask is reused unchanged for all tests in the match."
hint_level_3 = "Infer the mask from a sample pair using output == input ^ mask, then apply that mask."
contract = FunctionContract(
    parameter_types=("int", "list[list[int]]"),
    return_type="int",
    parameter_names=("value", "samples"),
)


def solve_xor_byte(value: int, key: int) -> int:
    return (value ^ key) & 0xFF


def variable_factory(
    rng: random.Random, _difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return {"key": rng.randint(1, 255)}


def case_factory(
    rng: random.Random, _difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    value = rng.randint(0, 255)
    key = int(params["key"])
    return TestCase(inputs=(value,), output=solve_xor_byte(value, key))


def shared_input_factory(
    params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return sample_pairs_shared_scalar_inputs(params, sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    require_arity(primary_inputs, expected=1)
    value = require_int_value(primary_inputs[0], label="value")
    key = require_variable_int(variables, name="key")
    return solve_xor_byte(value, key)
