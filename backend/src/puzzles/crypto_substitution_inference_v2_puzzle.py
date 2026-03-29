from __future__ import annotations

import random
import string
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    require_arity,
    require_str_value,
    require_variable_str,
    sample_pairs_shared_inputs,
)

template_key = "crypto-substitution-inference-v2"
theme = "Cryptography"
difficulties: tuple[Difficulty, ...] = ("hard",)
prompt = (
    "A deterministic character substitution is used across this match. "
    "`samples` contains visible (input, output) string pairs produced with the same hidden mapping. "
    "Implement solution(arg1, samples) so it applies that same mapping to `arg1`."
)
hint_level_1 = "Each source character always maps to exactly one target character."
hint_level_2 = (
    "The mapping is one-to-one and reused unchanged for all tests in the match."
)
hint_level_3 = (
    "Build a mapping table from example characters, then translate the input text."
)
contract = FunctionContract(
    parameter_types=("str", "list[tuple[str, str]]"),
    return_type="str",
    parameter_names=("arg1", "samples"),
)


def solve_substitution(text: str, source: str, target: str) -> str:
    mapping = {src: dst for src, dst in zip(source, target, strict=True)}
    return "".join(mapping.get(char, char) for char in text)


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    alphabet_size = {"easy": 5, "medium": 7, "hard": 9, "expert": 11}[difficulty]
    source_chars = rng.sample(list(string.ascii_lowercase), alphabet_size)
    source = "".join(source_chars)

    target_chars = source_chars[:]
    while target_chars == source_chars:
        rng.shuffle(target_chars)

    target = "".join(target_chars)
    return {"source": source, "target": target}


def case_factory(
    rng: random.Random, difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    source = str(params["source"])
    target = str(params["target"])
    source_chars = list(source)

    extras = {"easy": 8, "medium": 14, "hard": 22, "expert": 30}[difficulty]
    text_chars = source_chars + [rng.choice(source_chars) for _index in range(extras)]
    rng.shuffle(text_chars)
    source_text = "".join(text_chars)

    return TestCase(
        inputs=(source_text,),
        output=solve_substitution(source_text, source, target),
    )


def shared_input_factory(
    params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return sample_pairs_shared_inputs(params, sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    require_arity(primary_inputs, expected=1)
    text = require_str_value(primary_inputs[0], label="text")
    source = require_variable_str(variables, name="source")
    target = require_variable_str(variables, name="target")
    return solve_substitution(text, source, target)
