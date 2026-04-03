from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Sequence, cast

from puzzle import FunctionContract, PuzzleInstance, TestCase
from snekbox import execute_python

RUNTIME_TIMEOUT_SECONDS = 2.5
CUSTOM_THEME = "Custom"
CUSTOM_DIFFICULTY = "easy"
CUSTOM_HINT = "Infer the rule from the visible samples."
DEFAULT_CUSTOM_PUZZLE_SOURCE = """prompt = (
    "Given an integer input and a hidden match variable named `offset`, "
    "return the adjusted value."
)

contract = FunctionContract(
    parameter_types=("int",),
    return_type="int",
    parameter_names=("value",),
)


def variable_factory(rng: random.Random, _difficulty: Difficulty) -> dict[str, JsonScalar]:
    return {"offset": rng.randint(1, 9)}


def case_factory(
    rng: random.Random,
    _difficulty: Difficulty,
    params: dict[str, JsonScalar],
) -> TestCase:
    value = rng.randint(-20, 20)
    offset = require_variable_int(params, name="offset")
    return TestCase(inputs=(value,), output=value + offset)


def shared_input_factory(
    _params: dict[str, JsonScalar],
    _sample_tests: list[TestCase],
) -> tuple[Any, ...]:
    return no_shared_inputs(_params, _sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    require_arity(primary_inputs, expected=1)
    value = require_int_value(primary_inputs[0], label="value")
    offset = require_variable_int(variables, name="offset")
    return value + offset
"""

_RUNTIME_PATH = Path(__file__).with_name("custom_puzzle_runtime.py")
_RUNTIME_SOURCE = _RUNTIME_PATH.read_text(encoding="utf-8")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify_title(title: str) -> str:
    normalized = title.strip().casefold()
    collapsed = _SLUG_PATTERN.sub("-", normalized).strip("-")
    return collapsed or "custom-puzzle"


def custom_template_key(*, owner_id: str, puzzle_id: str) -> str:
    owner_token = re.sub(r"[^a-z0-9]", "", owner_id.casefold())
    puzzle_token = re.sub(r"[^a-z0-9]", "", puzzle_id.casefold())
    return f"user-{owner_token[:12]}-{puzzle_token[:12]}"


def validate_custom_puzzle_source(*, source_code: str, seed: int = 7) -> None:
    _run_runtime({"operation": "validate", "source_code": source_code, "seed": seed})


def build_custom_puzzle_instance(
    *,
    owner_id: str,
    puzzle_id: str,
    source_code: str,
    seed: int,
) -> PuzzleInstance:
    payload = _run_runtime(
        {
            "operation": "generate",
            "source_code": source_code,
            "seed": seed,
        }
    )
    return _puzzle_instance_from_runtime_payload(
        owner_id=owner_id,
        puzzle_id=puzzle_id,
        payload=payload,
    )


def expected_output_for_custom_primary_inputs(
    *,
    source_code: str,
    variables: dict[str, Any],
    primary_inputs: Sequence[Any],
) -> Any:
    payload = _run_runtime(
        {
            "operation": "expected_output",
            "source_code": source_code,
            "variables": variables,
            "primary_inputs": list(primary_inputs),
        }
    )
    return payload["expected_output"]


def _run_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        execution = execute_python(
            _runtime_script(payload),
            timeout_seconds=RUNTIME_TIMEOUT_SECONDS,
        )
    except ValueError as exc:
        raise ValueError(f"Custom puzzle sandbox request failed: {exc}") from None

    if execution.returncode != 0:
        if execution.returncode == 137:
            raise ValueError("Custom puzzle validation exceeded sandbox limits")
        detail = execution.stdout.strip()
        if not detail:
            detail = f"Sandbox returned code {execution.returncode}"
        raise ValueError(f"Custom puzzle validation failed: {detail}")

    decoded = _decode_json_line(execution.stdout)
    if decoded is None:
        raise ValueError("Custom puzzle validation failed without output")

    if not isinstance(decoded, dict):
        raise ValueError("Custom puzzle validation returned invalid payload")
    decoded_payload = cast(dict[str, object], decoded)
    if not decoded_payload.get("ok"):
        raise ValueError(
            str(decoded_payload.get("error", "Custom puzzle validation failed"))
        )

    result = decoded_payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("Custom puzzle validation returned invalid result")
    return cast(dict[str, Any], result)


def _runtime_script(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, separators=(",", ":"))
    return f"""{_RUNTIME_SOURCE}

print(json.dumps(run_payload(json.loads({encoded_payload!r})), separators=(",", ":")))
"""


def _decode_json_line(stdout: str) -> object:
    stripped_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(stripped_lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _puzzle_instance_from_runtime_payload(
    *,
    owner_id: str,
    puzzle_id: str,
    payload: dict[str, Any],
) -> PuzzleInstance:
    contract = _contract_from_payload(payload.get("contract"))
    variables = _json_scalars(payload.get("variables"))
    shared_inputs = tuple(
        _json_to_python(item)
        for item in _require_list(payload.get("shared_inputs"), "shared_inputs")
    )
    sample_tests = _cases_from_payload(payload.get("sample_tests"))
    hidden_tests = _cases_from_payload(payload.get("hidden_tests"))
    prompt = _require_string(payload.get("prompt"), "prompt")
    hint_level_1 = _require_string(payload.get("hint_level_1"), "hint_level_1")
    hint_level_2 = _require_string(payload.get("hint_level_2"), "hint_level_2")
    hint_level_3 = _require_string(payload.get("hint_level_3"), "hint_level_3")
    template_key = custom_template_key(owner_id=owner_id, puzzle_id=puzzle_id)

    fingerprint_payload = {
        "template": template_key,
        "theme": CUSTOM_THEME,
        "difficulty": CUSTOM_DIFFICULTY,
        "variables": variables,
        "contract": {
            "parameter_types": list(contract.parameter_types),
            "return_type": contract.return_type,
            "parameter_names": (
                None
                if contract.parameter_names is None
                else list(contract.parameter_names)
            ),
        },
        "shared_inputs": list(shared_inputs),
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    signature_payload = {
        **fingerprint_payload,
        "sample_tests": [_serialize_case(case) for case in sample_tests],
        "hidden_tests": [_serialize_case(case) for case in hidden_tests],
    }
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()

    return PuzzleInstance(
        id=fingerprint[:12],
        theme=CUSTOM_THEME,
        difficulty=CUSTOM_DIFFICULTY,
        prompt=prompt,
        sample_tests=sample_tests,
        hidden_tests=hidden_tests,
        hint_level_1=hint_level_1 or CUSTOM_HINT,
        hint_level_2=hint_level_2 or CUSTOM_HINT,
        hint_level_3=hint_level_3 or CUSTOM_HINT,
        variables=variables,
        contract=contract,
        template_key=template_key,
        shared_inputs=shared_inputs,
        fingerprint=fingerprint,
        signature=signature,
    )


def _contract_from_payload(value: object) -> FunctionContract:
    if not isinstance(value, dict):
        raise ValueError("contract payload is invalid")
    payload = cast(dict[str, object], value)
    parameter_types = payload.get("parameter_types")
    return_type = payload.get("return_type")
    parameter_names = payload.get("parameter_names")
    if not isinstance(parameter_types, list) or not all(
        isinstance(item, str) for item in parameter_types
    ):
        raise ValueError("contract parameter_types are invalid")
    if not isinstance(return_type, str):
        raise ValueError("contract return_type is invalid")
    parsed_parameter_names: tuple[str, ...] | None = None
    if parameter_names is not None:
        if not isinstance(parameter_names, list) or not all(
            isinstance(item, str) for item in parameter_names
        ):
            raise ValueError("contract parameter_names are invalid")
        parsed_parameter_names = cast(tuple[str, ...], tuple(parameter_names))
    return FunctionContract(
        parameter_types=cast(tuple[str, ...], tuple(parameter_types)),
        return_type=return_type,
        parameter_names=parsed_parameter_names,
    )


def _cases_from_payload(value: object) -> list[TestCase]:
    cases = _require_list(value, "cases")
    parsed: list[TestCase] = []
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("case payload is invalid")
        inputs = _require_list(item.get("inputs"), "inputs")
        parsed.append(
            TestCase(
                inputs=tuple(_json_to_python(entry) for entry in inputs),
                output=_json_to_python(item.get("output")),
            )
        )
    return parsed


def _serialize_case(case: TestCase) -> dict[str, Any]:
    return {
        "inputs": list(case.inputs),
        "output": case.output,
    }


def _json_scalars(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("variables payload is invalid")
    parsed: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("variable key is invalid")
        parsed[key] = _json_to_python(item)
    return parsed


def _json_to_python(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_to_python(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_to_python(item) for key, item in value.items()}
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} payload is invalid")
    return list(value)


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} payload is invalid")
    return value
