from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.ai_generated_common import (
    ai_case_factory,
    ai_contract_factory,
    ai_expected_output,
    ai_shared_input_factory,
    ai_variable_factory,
)

template_key = "ai-generated-easy-v1"
theme = "AI"
difficulties: tuple[Difficulty, ...] = ("easy",)
prompt = "{{ prompt_text }}"
hint_level_1 = "{{ hint_level_1_text }}"
hint_level_2 = "{{ hint_level_2_text }}"
hint_level_3 = "{{ hint_level_3_text }}"
contract = FunctionContract(
    parameter_types=("str", "list[tuple[str, str]]"),
    return_type="str",
    parameter_names=("arg1", "samples"),
)
distinct_sample_outputs = True


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return ai_variable_factory(rng, difficulty)


def contract_factory(variables: dict[str, JsonScalar]) -> FunctionContract:
    return ai_contract_factory(variables)


def case_factory(
    rng: random.Random, difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    return ai_case_factory(rng, difficulty, params)


def shared_input_factory(
    params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return ai_shared_input_factory(params, sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    return ai_expected_output(
        variables=variables,
        primary_inputs=primary_inputs,
    )
