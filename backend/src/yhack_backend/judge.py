from __future__ import annotations

import builtins
import inspect
import multiprocessing as mp
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Literal, cast

from .puzzle import TestCase

Verdict = Literal["accepted", "sample_failed", "wrong_answer", "error"]

_ALLOWED_BUILTINS = {
    name: getattr(builtins, name)
    for name in [
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "pow",
        "range",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    ]
}


@dataclass(frozen=True, slots=True)
class JudgeResult:
    verdict: Verdict
    sample_passed: int
    sample_total: int
    hidden_passed: int
    hidden_total: int
    runtime_ms: int
    message: str = ""


def judge_submission(
    code: str,
    sample_tests: list[TestCase],
    hidden_tests: list[TestCase],
    timeout_seconds: float = 1.0,
) -> JudgeResult:
    sample_passed = 0
    runtime_ms = 0

    for case in sample_tests:
        ok, output, error, elapsed_ms = _run_case(code, case.input_str, timeout_seconds)
        runtime_ms += elapsed_ms
        if not ok:
            return JudgeResult(
                verdict="error",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=0,
                hidden_total=len(hidden_tests),
                runtime_ms=runtime_ms,
                message=error,
            )
        if _normalize_output(output) != _normalize_output(case.output_str):
            return JudgeResult(
                verdict="sample_failed",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=0,
                hidden_total=len(hidden_tests),
                runtime_ms=runtime_ms,
                message="Sample tests failed",
            )
        sample_passed += 1

    hidden_passed = 0
    for case in hidden_tests:
        ok, output, error, elapsed_ms = _run_case(code, case.input_str, timeout_seconds)
        runtime_ms += elapsed_ms
        if not ok:
            return JudgeResult(
                verdict="error",
                sample_passed=sample_passed,
                sample_total=len(sample_tests),
                hidden_passed=hidden_passed,
                hidden_total=len(hidden_tests),
                runtime_ms=runtime_ms,
                message=error,
            )
        if _normalize_output(output) == _normalize_output(case.output_str):
            hidden_passed += 1

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
    )


def _run_case(
    code: str,
    input_str: str,
    timeout_seconds: float,
) -> tuple[bool, str, str, int]:
    queue: mp.Queue[tuple[str, str, str, int]] = mp.Queue(maxsize=1)
    proc = mp.Process(target=_worker, args=(code, input_str, queue), daemon=True)
    proc.start()
    proc.join(timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join()
        return (
            False,
            "",
            f"Timeout after {timeout_seconds:.2f}s",
            int(timeout_seconds * 1000),
        )

    if queue.empty():
        return (False, "", "Execution failed without output", 0)

    status, output, error, elapsed_ms = queue.get()
    return (status == "ok", output, error, elapsed_ms)


def _worker(
    code: str, input_str: str, queue: mp.Queue[tuple[str, str, str, int]]
) -> None:
    started = perf_counter()
    try:
        namespace: dict[str, object] = {"__builtins__": _ALLOWED_BUILTINS}
        compiled = compile(code, "<submission>", "exec")
        exec(compiled, namespace, namespace)

        solution_candidate = namespace.get("solution")
        if not callable(solution_candidate):
            raise TypeError("Missing solution(input_str) function")
        solution = cast(Callable[[str], object], solution_candidate)

        signature = inspect.signature(solution)
        if len(signature.parameters) != 1:
            raise TypeError("solution must take exactly one argument")

        output = solution(input_str)
        if not isinstance(output, str):
            raise TypeError("solution must return a string")

        elapsed_ms = int((perf_counter() - started) * 1000)
        queue.put(("ok", output, "", elapsed_ms))
    except BaseException as exc:  # noqa: BLE001
        elapsed_ms = int((perf_counter() - started) * 1000)
        queue.put(("error", "", f"{type(exc).__name__}: {exc}", elapsed_ms))


def _normalize_output(value: str) -> str:
    stripped_lines = [line.rstrip() for line in value.strip().splitlines()]
    return "\n".join(stripped_lines)
