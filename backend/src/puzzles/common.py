from __future__ import annotations

from typing import Any, Sequence, cast

from domain_types import JsonScalar


def no_variables(_: Any, __: Any) -> dict[str, JsonScalar]:
    return {}


def no_shared_inputs(
    _params: dict[str, JsonScalar], _sample_tests: list[Any]
) -> tuple[Any, ...]:
    return ()


def sample_pairs_shared_inputs(
    _params: dict[str, JsonScalar], sample_tests: list[Any]
) -> tuple[Any, ...]:
    pairs: list[tuple[str, str]] = []
    for case in sample_tests:
        if len(case.inputs) != 1:
            raise ValueError("Expected one primary input for sample-pair context")
        input_value = case.inputs[0]
        if not isinstance(input_value, str) or not isinstance(case.output, str):
            raise ValueError("Sample-pair context requires string-to-string cases")
        pairs.append((input_value, case.output))
    return (pairs,)


def sample_pairs_shared_scalar_inputs(
    _params: dict[str, JsonScalar], sample_tests: list[Any]
) -> tuple[Any, ...]:
    pairs: list[list[JsonScalar]] = []
    for case in sample_tests:
        if len(case.inputs) != 1:
            raise ValueError("Expected one primary input for sample-pair context")
        input_value = case.inputs[0]
        if not is_scalar(input_value) or not is_scalar(case.output):
            raise ValueError("Sample-pair context requires scalar-to-scalar cases")
        pairs.append([cast(JsonScalar, input_value), cast(JsonScalar, case.output)])
    return (pairs,)


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def require_arity(values: Sequence[Any], *, expected: int) -> None:
    if len(values) != expected:
        raise ValueError(f"inputs must contain exactly {expected} argument(s)")


def require_int_value(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def require_str_value(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def require_int_sequence(value: Any, *, label: str) -> list[int]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of integers")
    parsed: list[int] = []
    for index, item in enumerate(value):
        parsed.append(require_int_value(item, label=f"{label}[{index}]"))
    return parsed


def require_str_sequence(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list of strings")
    parsed: list[str] = []
    for index, item in enumerate(value):
        parsed.append(require_str_value(item, label=f"{label}[{index}]"))
    return parsed


def require_intervals(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        raise ValueError("intervals must be a list")
    intervals: list[tuple[int, int]] = []
    for index, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"interval[{index}] must be a two-item list")
        start = require_int_value(item[0], label=f"interval[{index}][0]")
        end = require_int_value(item[1], label=f"interval[{index}][1]")
        intervals.append((start, end))
    return intervals


def require_variable_int(variables: dict[str, JsonScalar], *, name: str) -> int:
    value = variables.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Puzzle variable {name} must be an integer")
    return value


def require_variable_str(variables: dict[str, JsonScalar], *, name: str) -> str:
    value = variables.get(name)
    if not isinstance(value, str):
        raise ValueError(f"Puzzle variable {name} must be a string")
    return value
