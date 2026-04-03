from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Literal, cast

from puzzle import (
    FunctionContract,
    TestCase,
    format_case_input,
    format_value,
    invocation_inputs,
)
from snekbox import execute_python

Verdict = Literal["accepted", "sample_failed", "wrong_answer", "error"]


@dataclass(frozen=True, slots=True)
class FailedHiddenTest:
    input_str: str
    expected_output: str
    actual_output: str


@dataclass(frozen=True, slots=True)
class JudgeResult:
    verdict: Verdict
    sample_passed: int
    sample_total: int
    hidden_passed: int
    hidden_total: int
    runtime_ms: int
    message: str = ""
    stdout: str = ""
    first_failed_hidden_test: FailedHiddenTest | None = None
    first_failed_hidden_case: TestCase | None = None


def judge_submission(
    code: str,
    sample_tests: list[TestCase],
    hidden_tests: list[TestCase],
    contract: FunctionContract,
    shared_inputs: tuple[Any, ...] = (),
    timeout_seconds: float = 1.0,
    include_hidden_tests: bool = True,
) -> JudgeResult:
    sample_passed = 0
    runtime_ms = 0
    stdout_chunks: list[str] = []
    hidden_total = len(hidden_tests) if include_hidden_tests else 0

    for case_index, case in enumerate(sample_tests, start=1):
        call_inputs = invocation_inputs(case, shared_inputs)
        ok, output, error, elapsed_ms, stdout = _run_case(
            code,
            call_inputs,
            contract,
            timeout_seconds,
        )
        runtime_ms += elapsed_ms
        _append_stdout(stdout_chunks, "sample", case_index, stdout)
        if not ok:
            return JudgeResult(
                verdict="error",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=0,
                hidden_total=hidden_total,
                runtime_ms=runtime_ms,
                message=error,
                stdout=_combine_stdout(stdout_chunks),
            )
        if not _values_equal(output, case.output):
            return JudgeResult(
                verdict="sample_failed",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=0,
                hidden_total=hidden_total,
                runtime_ms=runtime_ms,
                message="Sample tests failed",
                stdout=_combine_stdout(stdout_chunks),
            )
        sample_passed += 1

    if not include_hidden_tests:
        return JudgeResult(
            verdict="accepted",
            sample_passed=sample_passed,
            sample_total=len(sample_tests),
            hidden_passed=0,
            hidden_total=0,
            runtime_ms=runtime_ms,
            stdout=_combine_stdout(stdout_chunks),
        )

    hidden_passed = 0
    first_failed_hidden_test: FailedHiddenTest | None = None
    first_failed_hidden_case: TestCase | None = None
    for case_index, case in enumerate(hidden_tests, start=1):
        call_inputs = invocation_inputs(case, shared_inputs)
        ok, output, error, elapsed_ms, stdout = _run_case(
            code,
            call_inputs,
            contract,
            timeout_seconds,
        )
        runtime_ms += elapsed_ms
        _append_stdout(stdout_chunks, "hidden", case_index, stdout)
        if not ok:
            return JudgeResult(
                verdict="error",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=hidden_passed,
                hidden_total=len(hidden_tests),
                runtime_ms=runtime_ms,
                message=error,
                stdout=_combine_stdout(stdout_chunks),
                first_failed_hidden_test=first_failed_hidden_test,
                first_failed_hidden_case=first_failed_hidden_case,
            )
        if _values_equal(output, case.output):
            hidden_passed += 1
            continue

        if first_failed_hidden_test is None:
            first_failed_hidden_test = FailedHiddenTest(
                input_str=format_case_input(case.inputs),
                expected_output=format_value(case.output),
                actual_output=format_value(output),
            )
            first_failed_hidden_case = case

    verdict: Verdict = (
        "accepted" if hidden_passed == len(hidden_tests) else "wrong_answer"
    )
    message = (
        ""
        if verdict == "accepted"
        else f"Passed hidden tests: {hidden_passed}/{len(hidden_tests)}"
    )

    return JudgeResult(
        verdict=verdict,
        sample_passed=sample_passed,
        sample_total=len(sample_tests),
        hidden_passed=hidden_passed,
        hidden_total=len(hidden_tests),
        runtime_ms=runtime_ms,
        message=message,
        stdout=_combine_stdout(stdout_chunks),
        first_failed_hidden_test=first_failed_hidden_test,
        first_failed_hidden_case=first_failed_hidden_case,
    )


def _run_case(
    code: str,
    inputs: tuple[Any, ...],
    contract: FunctionContract,
    timeout_seconds: float,
) -> tuple[bool, Any, str, int, str]:
    payload = {
        "code": code,
        "inputs": list(inputs),
        "expected_arity": len(contract.parameter_types),
    }
    started = perf_counter()
    try:
        execution = execute_python(
            _runner_script(payload),
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return (False, "", str(exc), elapsed_ms, "")
    elapsed_ms = int((perf_counter() - started) * 1000)

    if execution.returncode != 0:
        if execution.returncode == 137:
            return (
                False,
                "",
                "Sandbox execution exceeded time or memory limits",
                elapsed_ms,
                "",
            )
        output = execution.stdout.strip()
        detail = output or f"Sandbox returned code {execution.returncode}"
        return (False, "", detail, elapsed_ms, "")

    decoded = _decode_json_line(execution.stdout)
    if not isinstance(decoded, dict):
        return (False, "", "Sandbox returned invalid payload", elapsed_ms, "")
    decoded_payload = cast(dict[str, object], decoded)

    ok = bool(decoded_payload.get("ok"))
    stdout = decoded_payload.get("stdout")
    if not isinstance(stdout, str):
        stdout = ""

    if not ok:
        error = decoded_payload.get("error")
        if not isinstance(error, str) or not error:
            error = "Execution failed"
        return (False, "", error, elapsed_ms, stdout)

    return (True, decoded_payload.get("output"), "", elapsed_ms, stdout)


def _runner_script(payload: dict[str, Any]) -> str:
    encoded_payload = json.dumps(payload, separators=(",", ":"))
    return f"""
import contextlib
import inspect
import io
import json

PAYLOAD = json.loads({encoded_payload!r})


def _normalize_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {{
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }}
    if isinstance(value, set):
        return sorted((_normalize_value(item) for item in value), key=repr)
    raise TypeError(
        "Unsupported return type from solution. "
        "Use primitives, lists, tuples, dicts, or sets."
    )


def _run():
    stdout_capture = io.StringIO()
    try:
        namespace = {{}}
        with contextlib.redirect_stdout(stdout_capture):
            compiled = compile(PAYLOAD["code"], "<submission>", "exec")
            exec(compiled, namespace, namespace)

            solution_candidate = namespace.get("solution")
            if not callable(solution_candidate):
                raise TypeError("Missing solution function")

            signature = inspect.signature(solution_candidate)
            expected_arity = PAYLOAD["expected_arity"]
            if len(signature.parameters) != expected_arity:
                raise TypeError(
                    f"solution must take exactly {{expected_arity}} argument"
                    f"{{'s' if expected_arity != 1 else ''}}"
                )

            output = solution_candidate(*PAYLOAD["inputs"])
            normalized_output = _normalize_value(output)

        result = {{
            "ok": True,
            "output": normalized_output,
            "stdout": stdout_capture.getvalue(),
        }}
    except BaseException as exc:
        result = {{
            "ok": False,
            "error": f"{{type(exc).__name__}}: {{exc}}",
            "stdout": stdout_capture.getvalue(),
        }}

    print(json.dumps(result, separators=(",", ":")))


_run()
"""


def _decode_json_line(stdout: str) -> object:
    stripped_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(stripped_lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _values_equal(actual: Any, expected: Any) -> bool:
    return _normalize_value(actual) == _normalize_value(expected)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, set):
        return sorted((_normalize_value(item) for item in value), key=repr)
    raise TypeError(
        "Unsupported return type from solution. "
        "Use primitives, lists, tuples, dicts, or sets."
    )


def _append_stdout(
    chunks: list[str],
    bucket: Literal["sample", "hidden"],
    case_index: int,
    stdout: str,
) -> None:
    if not stdout:
        return

    normalized = stdout if stdout.endswith("\n") else f"{stdout}\n"
    chunks.append(f"[{bucket} {case_index}]\n{normalized}")


def _combine_stdout(chunks: list[str]) -> str:
    return "\n".join(chunks).rstrip()
