from __future__ import annotations

import builtins
import contextlib
from dataclasses import dataclass
import io
import inspect
import multiprocessing as mp
from time import perf_counter
from typing import Callable, Literal, cast

from puzzle import TestCase

Verdict = Literal["accepted", "sample_failed", "wrong_answer", "error"]

_BLOCKED_BUILTINS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "vars",
}

_ALLOWED_BUILTINS = {
    name: value
    for name, value in builtins.__dict__.items()
    if name not in _BLOCKED_BUILTINS
}


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


def judge_submission(
    code: str,
    sample_tests: list[TestCase],
    hidden_tests: list[TestCase],
    timeout_seconds: float = 1.0,
    include_hidden_tests: bool = True,
) -> JudgeResult:
    sample_passed = 0
    runtime_ms = 0
    stdout_chunks: list[str] = []
    hidden_total = len(hidden_tests) if include_hidden_tests else 0

    for case_index, case in enumerate(sample_tests, start=1):
        ok, output, error, elapsed_ms, stdout = _run_case(
            code,
            case.input_str,
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
        if _normalize_output(output) != _normalize_output(case.output_str):
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
    for case_index, case in enumerate(hidden_tests, start=1):
        ok, output, error, elapsed_ms, stdout = _run_case(
            code,
            case.input_str,
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
            )
        if _normalize_output(output) == _normalize_output(case.output_str):
            hidden_passed += 1
            continue

        if first_failed_hidden_test is None:
            first_failed_hidden_test = FailedHiddenTest(
                input_str=case.input_str,
                expected_output=case.output_str,
                actual_output=output,
            )

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
    )


def _run_case(
    code: str,
    input_str: str,
    timeout_seconds: float,
) -> tuple[bool, str, str, int, str]:
    queue: mp.Queue[tuple[str, str, str, int, str]] = mp.Queue(maxsize=1)
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
            "",
        )

    if queue.empty():
        return (False, "", "Execution failed without output", 0, "")

    status, output, error, elapsed_ms, stdout = queue.get()
    return (status == "ok", output, error, elapsed_ms, stdout)


def _worker(
    code: str,
    input_str: str,
    queue: mp.Queue[tuple[str, str, str, int, str]],
) -> None:
    started = perf_counter()
    stdout_capture = io.StringIO()
    try:
        namespace: dict[str, object] = {"__builtins__": _ALLOWED_BUILTINS}
        with contextlib.redirect_stdout(stdout_capture):
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
        queue.put(("ok", output, "", elapsed_ms, stdout_capture.getvalue()))
    except BaseException as exc:  # noqa: BLE001
        elapsed_ms = int((perf_counter() - started) * 1000)
        queue.put(
            (
                "error",
                "",
                f"{type(exc).__name__}: {exc}",
                elapsed_ms,
                stdout_capture.getvalue(),
            )
        )


def _normalize_output(value: str) -> str:
    stripped_lines = [line.rstrip() for line in value.strip().splitlines()]
    return "\n".join(stripped_lines)


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
