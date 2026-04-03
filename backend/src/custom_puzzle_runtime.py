from __future__ import annotations

import ast
import json
import random
import sys
from typing import Any, Sequence, cast

from domain_types import Difficulty, JsonScalar, JsonValue
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    is_scalar,
    no_shared_inputs,
    require_arity,
    require_int_sequence,
    require_int_value,
    require_intervals,
    require_str_sequence,
    require_str_value,
    require_variable_int,
    require_variable_str,
    sample_pairs_shared_inputs,
    sample_pairs_shared_json_inputs,
    sample_pairs_shared_scalar_inputs,
)

CUSTOM_DIFFICULTY: Difficulty = "easy"
CUSTOM_HINT = "Infer the rule from the visible samples."
CUSTOM_HIDDEN_TEST_COUNT = 10
MAX_CASE_ATTEMPTS = 400

_FORBIDDEN_TOP_LEVEL_EXPORTS = {
    "template_key",
    "theme",
    "difficulties",
    "hint_level_1",
    "hint_level_2",
    "hint_level_3",
}
_REQUIRED_EXPORTS = {
    "prompt",
    "contract",
    "variable_factory",
    "case_factory",
    "shared_input_factory",
    "expected_output_for_primary_inputs",
}
_OPTIONAL_EXPORTS = {"contract_factory", "distinct_sample_outputs"}
_FORBIDDEN_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "memoryview",
    "object",
    "open",
    "setattr",
    "super",
    "type",
    "vars",
}
_FORBIDDEN_MODULE_NAMES = {
    "builtins",
    "ctypes",
    "importlib",
    "io",
    "os",
    "pathlib",
    "socket",
    "subprocess",
    "sys",
}
_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}
_SANDBOX_GLOBALS: dict[str, Any] = {
    "__builtins__": _SAFE_BUILTINS,
    "Any": Any,
    "Difficulty": Difficulty,
    "FunctionContract": FunctionContract,
    "JsonScalar": JsonScalar,
    "Sequence": Sequence,
    "TestCase": TestCase,
    "CUSTOM_HINT": CUSTOM_HINT,
    "CUSTOM_DIFFICULTY": CUSTOM_DIFFICULTY,
    "is_scalar": is_scalar,
    "no_shared_inputs": no_shared_inputs,
    "random": random,
    "require_arity": require_arity,
    "require_int_sequence": require_int_sequence,
    "require_int_value": require_int_value,
    "require_intervals": require_intervals,
    "require_str_sequence": require_str_sequence,
    "require_str_value": require_str_value,
    "require_variable_int": require_variable_int,
    "require_variable_str": require_variable_str,
    "sample_pairs_shared_inputs": sample_pairs_shared_inputs,
    "sample_pairs_shared_json_inputs": sample_pairs_shared_json_inputs,
    "sample_pairs_shared_scalar_inputs": sample_pairs_shared_scalar_inputs,
}


def main() -> None:
    raw = sys.stdin.read()
    if not raw:
        _write_error("Missing payload")
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        _write_error("Invalid JSON payload")
        return

    try:
        result = _handle(payload)
    except Exception as exc:  # pragma: no cover - exercised via subprocess boundary
        _write_error(str(exc))
        return

    sys.stdout.write(json.dumps({"ok": True, "result": result}))


def _handle(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Payload must be an object")
    parsed = cast(dict[str, object], payload)

    source_code = parsed.get("source_code")
    if not isinstance(source_code, str) or not source_code.strip():
        raise ValueError("source_code is required")
    if len(source_code) > 60_000:
        raise ValueError("source_code is too large")

    operation = parsed.get("operation")
    if operation not in {"validate", "generate", "expected_output"}:
        raise ValueError("Unsupported operation")

    exports = _load_exports(source_code)

    if operation == "validate":
        seed = _coerce_seed(parsed.get("seed"))
        _generate_snapshot(exports, seed=seed)
        return {"validated": True}

    if operation == "generate":
        seed = _coerce_seed(parsed.get("seed"))
        return _generate_snapshot(exports, seed=seed)

    variables = _coerce_variables(parsed.get("variables"))
    primary_inputs = parsed.get("primary_inputs")
    if not isinstance(primary_inputs, list):
        raise ValueError("primary_inputs must be a list")
    output = exports["expected_output_for_primary_inputs"](
        variables=variables,
        primary_inputs=primary_inputs,
    )
    return {"expected_output": _json_value(output)}


def _coerce_seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("seed must be numeric")
    return int(value)


def _coerce_variables(value: object) -> dict[str, JsonScalar]:
    if not isinstance(value, dict):
        raise ValueError("variables must be an object")
    variables: dict[str, JsonScalar] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("variable keys must be strings")
        if not isinstance(item, (str, int, float, bool)):
            raise ValueError("variables must use JSON scalar values")
        variables[key] = item
    return variables


def _load_exports(source_code: str) -> dict[str, Any]:
    tree = ast.parse(source_code, mode="exec")
    _validate_ast(tree)

    module_globals = dict(_SANDBOX_GLOBALS)
    exec(compile(tree, "<user-puzzle>", "exec"), module_globals, module_globals)

    for name in _FORBIDDEN_TOP_LEVEL_EXPORTS:
        if name in module_globals:
            raise ValueError(f"{name} is managed by the system")

    missing = [name for name in _REQUIRED_EXPORTS if name not in module_globals]
    if missing:
        raise ValueError(f"Missing required export(s): {', '.join(sorted(missing))}")

    prompt = module_globals["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    contract = module_globals["contract"]
    if not isinstance(contract, FunctionContract):
        raise ValueError("contract must be FunctionContract")

    for name in (
        "variable_factory",
        "case_factory",
        "shared_input_factory",
        "expected_output_for_primary_inputs",
    ):
        if not callable(module_globals[name]):
            raise ValueError(f"{name} must be callable")

    contract_factory = module_globals.get("contract_factory")
    if contract_factory is not None and not callable(contract_factory):
        raise ValueError("contract_factory must be callable")

    distinct_sample_outputs = bool(module_globals.get("distinct_sample_outputs", False))

    return {
        "prompt": prompt.strip(),
        "contract": contract,
        "contract_factory": contract_factory,
        "variable_factory": module_globals["variable_factory"],
        "case_factory": module_globals["case_factory"],
        "shared_input_factory": module_globals["shared_input_factory"],
        "expected_output_for_primary_inputs": module_globals[
            "expected_output_for_primary_inputs"
        ],
        "distinct_sample_outputs": distinct_sample_outputs,
    }


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Imports are not allowed in custom puzzle source")
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Try, ast.With)):
            raise ValueError("Unsupported Python construct in custom puzzle source")
        if isinstance(node, ast.Raise):
            raise ValueError("raise is not allowed in custom puzzle source")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise ValueError(f"{node.id} is not allowed in custom puzzle source")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_MODULE_NAMES:
            raise ValueError(f"{node.id} is not available in custom puzzle source")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attribute access is not allowed")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _validate_assignment_target(target)
        if isinstance(node, ast.AnnAssign):
            _validate_assignment_target(node.target)


def _validate_assignment_target(target: ast.expr) -> None:
    if isinstance(target, ast.Name) and target.id in _FORBIDDEN_TOP_LEVEL_EXPORTS:
        raise ValueError(f"{target.id} is managed by the system")


def _generate_snapshot(exports: dict[str, Any], *, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    variables = exports["variable_factory"](rng, CUSTOM_DIFFICULTY)
    if not isinstance(variables, dict):
        raise ValueError("variable_factory must return a dict")
    normalized_variables = _coerce_variables(variables)

    contract = exports["contract"]
    contract_factory = exports["contract_factory"]
    if contract_factory is not None:
        contract = contract_factory(normalized_variables)
    if not isinstance(contract, FunctionContract):
        raise ValueError("contract_factory must return FunctionContract")

    sample_tests = _build_cases(
        exports,
        rng=rng,
        variables=normalized_variables,
        count=3,
        distinct_outputs=exports["distinct_sample_outputs"],
    )
    shared_inputs = exports["shared_input_factory"](normalized_variables, sample_tests)
    if not isinstance(shared_inputs, tuple):
        raise ValueError("shared_input_factory must return a tuple")
    hidden_tests = _build_cases(
        exports,
        rng=rng,
        variables=normalized_variables,
        count=CUSTOM_HIDDEN_TEST_COUNT,
        existing_cases=sample_tests,
    )

    # Verify the exported expected_output helper matches visible and hidden cases.
    for case in [*sample_tests, *hidden_tests]:
        expected = exports["expected_output_for_primary_inputs"](
            variables=normalized_variables,
            primary_inputs=list(case.inputs),
        )
        if _json_value(expected) != _json_value(case.output):
            raise ValueError(
                "expected_output_for_primary_inputs must match generated case outputs"
            )

    return {
        "prompt": exports["prompt"],
        "hint_level_1": CUSTOM_HINT,
        "hint_level_2": CUSTOM_HINT,
        "hint_level_3": CUSTOM_HINT,
        "variables": normalized_variables,
        "contract": {
            "parameter_types": list(contract.parameter_types),
            "return_type": contract.return_type,
            "parameter_names": (
                None if contract.parameter_names is None else list(contract.parameter_names)
            ),
        },
        "shared_inputs": _json_value(list(shared_inputs)),
        "sample_tests": [_serialize_case(case) for case in sample_tests],
        "hidden_tests": [_serialize_case(case) for case in hidden_tests],
    }


def _build_cases(
    exports: dict[str, Any],
    *,
    rng: random.Random,
    variables: dict[str, JsonScalar],
    count: int,
    existing_cases: Sequence[TestCase] | None = None,
    distinct_outputs: bool = False,
) -> list[TestCase]:
    cases: list[TestCase] = []
    seen_signatures = {_case_signature(case) for case in (existing_cases or [])}
    seen_outputs = (
        {_case_output_signature(case) for case in (existing_cases or [])}
        if distinct_outputs
        else set()
    )

    attempts = 0
    while len(cases) < count and attempts < MAX_CASE_ATTEMPTS:
        attempts += 1
        case = exports["case_factory"](rng, CUSTOM_DIFFICULTY, variables)
        if not isinstance(case, TestCase):
            raise ValueError("case_factory must return TestCase")

        signature = _case_signature(case)
        if signature in seen_signatures:
            continue
        if distinct_outputs:
            output_signature = _case_output_signature(case)
            if output_signature in seen_outputs:
                continue
            seen_outputs.add(output_signature)
        seen_signatures.add(signature)
        cases.append(case)

    if len(cases) != count:
        raise ValueError("Unable to generate enough unique test cases")
    return cases


def _serialize_case(case: TestCase) -> dict[str, JsonValue]:
    return {
        "inputs": _json_value(list(case.inputs)),
        "output": _json_value(case.output),
    }


def _case_signature(case: TestCase) -> str:
    return json.dumps(_serialize_case(case), sort_keys=True, separators=(",", ":"))


def _case_output_signature(case: TestCase) -> str:
    return json.dumps(_json_value(case.output), sort_keys=True, separators=(",", ":"))


def _json_value(value: Any) -> JsonValue:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"Unsupported value type: {type(value).__name__}")


def _write_error(message: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "error": message}))


if __name__ == "__main__":
    main()
