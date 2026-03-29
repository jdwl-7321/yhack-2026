from judge import judge_submission
from puzzle import FunctionContract, TestCase


def test_accepts_valid_solution() -> None:
    sample = [TestCase((1, 2, 3), 6)]
    hidden = [TestCase((4, 5, 6), 15)]
    code = """
def solution(arg1: int, arg2: int, arg3: int) -> int:
    return arg1 + arg2 + arg3
"""

    result = judge_submission(
        code,
        sample,
        hidden,
        contract=FunctionContract(("int", "int", "int"), "int"),
    )
    assert result.verdict == "accepted"
    assert result.hidden_passed == 1


def test_rejects_missing_solution_function() -> None:
    result = judge_submission(
        "x = 1",
        [TestCase((1,), 1)],
        [TestCase((2,), 2)],
        contract=FunctionContract(("int",), "int"),
    )
    assert result.verdict == "error"
    assert "Missing solution" in result.message


def test_rejects_wrong_solution_arity() -> None:
    code = """
def solution(arg1: int) -> int:
    return arg1
"""
    result = judge_submission(
        code,
        [TestCase(([1, 2], 3), (0, 1))],
        [TestCase(([4, 5], 9), (0, 1))],
        contract=FunctionContract(("list[int]", "int"), "tuple[int, int]"),
    )
    assert result.verdict == "error"
    assert "exactly 2 arguments" in result.message


def test_sample_failure_short_circuits_hidden() -> None:
    code = """
def solution(arg1: list[int], arg2: int) -> tuple[int, int]:
    return (0, 0)
"""
    result = judge_submission(
        code,
        [TestCase(([1, 2, 3], 5), (1, 2))],
        [TestCase(([2, 8], 10), (0, 1))],
        contract=FunctionContract(("list[int]", "int"), "tuple[int, int]"),
    )
    assert result.verdict == "sample_failed"
    assert result.hidden_passed == 0


def test_allows_stdlib_builtins_and_captures_stdout() -> None:
    code = """
def solution(arg1: str) -> int:
    print("debug", ord("a"))
    return len(arg1)
"""
    result = judge_submission(
        code,
        [TestCase(("ab",), 2)],
        [TestCase(("xyz",), 3)],
        contract=FunctionContract(("str",), "int"),
    )
    assert result.verdict == "accepted"
    assert "debug 97" in result.stdout


def test_test_mode_skips_hidden_suite() -> None:
    code = """
def solution(arg1: str) -> int:
    return len(arg1)
"""
    result = judge_submission(
        code,
        [TestCase(("ab",), 2)],
        [TestCase(("abc",), 0)],
        contract=FunctionContract(("str",), "int"),
        include_hidden_tests=False,
    )
    assert result.verdict == "accepted"
    assert result.hidden_total == 0
    assert result.hidden_passed == 0


def test_returns_first_failed_hidden_test_and_case() -> None:
    code = """
def solution(arg1: int, arg2: int) -> tuple[int, int]:
    return (arg2, arg1)
"""
    result = judge_submission(
        code,
        [TestCase((1, 2), (2, 1))],
        [TestCase((3, 7), (3, 7)), TestCase((5, 9), (5, 9))],
        contract=FunctionContract(("int", "int"), "tuple[int, int]"),
    )
    assert result.verdict == "wrong_answer"
    assert result.first_failed_hidden_test is not None
    assert "arg1 = 3" in result.first_failed_hidden_test.input_str
    assert result.first_failed_hidden_case == TestCase((3, 7), (3, 7))


def test_normalizes_tuple_and_list_outputs_for_comparison() -> None:
    code = """
def solution(arg1: list[int], arg2: int):
    for left in range(len(arg1)):
        for right in range(left + 1, len(arg1)):
            if arg1[left] + arg1[right] == arg2:
                return [left, right]
    return []
"""
    result = judge_submission(
        code,
        [TestCase(([2, 7, 11, 15], 9), (0, 1))],
        [TestCase(([3, 2, 4], 6), (1, 2))],
        contract=FunctionContract(("list[int]", "int"), "tuple[int, int]"),
    )
    assert result.verdict == "accepted"


def test_supports_shared_context_inputs() -> None:
    code = """
def solution(arg1: str, arg2: list[tuple[str, str]]) -> str:
    mapping = {left: right for left, right in arg2}
    return mapping[arg1]
"""
    result = judge_submission(
        code,
        [TestCase(("ab",), "cd")],
        [TestCase(("ba",), "dc")],
        contract=FunctionContract(("str", "list[tuple[str, str]]"), "str"),
        shared_inputs=([("ab", "cd"), ("ba", "dc")],),
    )
    assert result.verdict == "accepted"
