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
)

template_key = "crypto-lsb-steganography-v1"
theme = "Cryptography"
difficulties: tuple[Difficulty, ...] = ("expert",)
prompt = "Given a list of integers, decode the hidden text value implied by the samples and return it as a string."
hint_level_1 = "Each integer contributes exactly one binary digit."
hint_level_2 = "That digit is determined by whether the integer is odd or even."
hint_level_3 = "Read least-significant bits in order, group every 8 bits, and decode ASCII characters."
contract = FunctionContract(
    parameter_types=("list[int]",),
    return_type="str",
    parameter_names=("numbers",),
)
distinct_sample_outputs = True


def decode_lsb_ascii(values: Sequence[int]) -> str:
    if len(values) % 8 != 0:
        raise ValueError("Encoded value count must be a multiple of 8")

    chars: list[str] = []
    for start in range(0, len(values), 8):
        chunk = values[start : start + 8]
        byte = 0
        for value in chunk:
            byte = (byte << 1) | (value & 1)
        chars.append(chr(byte))
    return "".join(chars)


def encode_word_as_lsb_values(rng: random.Random, word: str) -> list[int]:
    bits = "".join(f"{ord(char):08b}" for char in word)
    values: list[int] = []

    for bit in bits:
        value = rng.randint(0, 255)
        if bit == "1":
            value |= 1
        else:
            value &= ~1

        if rng.random() < 0.25:
            value += 256 * rng.randint(1, 3)
        values.append(value)

    return values


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    words_by_difficulty = {
        "easy": ["tree", "code", "salt", "mint", "bird", "game", "book"],
        "medium": ["cipher", "planet", "rocket", "winter", "bridge", "forest"],
        "hard": [
            "quantum",
            "network",
            "library",
            "orchard",
            "compass",
            "harvest",
        ],
        "expert": [
            "sandwich",
            "bluebird",
            "notebook",
            "elephant",
            "sunshine",
            "hardware",
        ],
    }
    word = rng.choice(words_by_difficulty[difficulty])
    encoded = encode_word_as_lsb_values(rng, word)
    decoded = decode_lsb_ascii(encoded)
    return TestCase(inputs=(encoded,), output=decoded)


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
    values = require_int_sequence(primary_inputs[0], label="numbers")
    return decode_lsb_ascii(values)
