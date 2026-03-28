from yhack_backend.judge import judge_submission
from yhack_backend.puzzle import TestCase


def test_accepts_valid_solution() -> None:
    sample = [TestCase("1 2 3", "3")]
    hidden = [TestCase("4 5", "2")]
    code = """
def solution(input_str: str) -> str:
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
def solution(input_str: str) -> str:
    return 1
"""
    result = judge_submission(code, [TestCase("x", "x")], [TestCase("y", "y")])
    assert result.verdict == "error"
    assert "return a string" in result.message


def test_sample_failure_short_circuits_hidden() -> None:
    code = """
def solution(input_str: str) -> str:
    return "wrong"
"""
    result = judge_submission(
        code,
        [TestCase("1", "right")],
        [TestCase("2", "hidden")],
    )
    assert result.verdict == "sample_failed"
    assert result.hidden_passed == 0
