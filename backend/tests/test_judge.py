from judge import judge_submission
from puzzle import TestCase


def test_accepts_valid_solution() -> None:
    sample = [TestCase("1 2 3", "3")]
    hidden = [TestCase("4 5", "2")]
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    return str(len(input_str.split()))
"""

    result = judge_submission(code, sample, hidden)
    assert result.verdict == "accepted"
    assert result.hidden_passed == 1


def test_rejects_missing_solution_function() -> None:
    result = judge_submission("x = 1", [TestCase("x", "x")], [TestCase("y", "y")])
    assert result.verdict == "error"
    assert "Missing solution" in result.message


def test_rejects_non_string_return() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    return 1
"""
    result = judge_submission(code, [TestCase("x", "x")], [TestCase("y", "y")])
    assert result.verdict == "error"
    assert "return a string" in result.message


def test_sample_failure_short_circuits_hidden() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    return "wrong"
"""
    result = judge_submission(
        code,
        [TestCase("1", "right")],
        [TestCase("2", "hidden")],
    )
    assert result.verdict == "sample_failed"
    assert result.hidden_passed == 0


def test_allows_stdlib_builtins_and_captures_stdout() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    print("debug", ord("a"))
    return str(len(input_str.split()))
"""
    result = judge_submission(code, [TestCase("1 2", "2")], [TestCase("x", "1")])
    assert result.verdict == "accepted"
    assert "debug 97" in result.stdout


def test_test_mode_skips_hidden_suite() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    return str(len(input_str.split()))
"""
    result = judge_submission(
        code,
        [TestCase("1 2", "2")],
        [TestCase("a b c", "0")],
        include_hidden_tests=False,
    )
    assert result.verdict == "accepted"
    assert result.hidden_total == 0
    assert result.hidden_passed == 0


def test_returns_first_failed_hidden_test() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    return "ok"
"""
    result = judge_submission(
        code,
        [TestCase("sample", "ok")],
        [TestCase("hidden 1", "bad"), TestCase("hidden 2", "bad")],
    )
    assert result.verdict == "wrong_answer"
    assert result.first_failed_hidden_test is not None
    assert result.first_failed_hidden_test.input_str == "hidden 1"
    assert result.first_failed_hidden_test.expected_output == "bad"
    assert result.first_failed_hidden_test.actual_output == "ok"


def test_solution_can_use_visible_samples_to_solve_hidden_cases() -> None:
    code = """
def solution(input_str: str, sample_cases: list[tuple[str, str]]) -> str:
    source, target = sample_cases[0]
    shift = (ord(target[0]) - ord(source[0])) % 26

    encoded: list[str] = []
    for char in input_str:
        if "a" <= char <= "z":
            encoded.append(chr((ord(char) - ord("a") + shift) % 26 + ord("a")))
        else:
            encoded.append(char)
    return "".join(encoded)
"""
    sample = [TestCase("abc", "def"), TestCase("xyz", "abc")]
    hidden = [TestCase("cab", "fde")]
    result = judge_submission(code, sample, hidden)
    assert result.verdict == "accepted"
