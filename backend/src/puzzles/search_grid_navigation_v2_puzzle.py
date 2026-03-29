from __future__ import annotations

from collections import deque
import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    no_shared_inputs,
    no_variables,
    require_arity,
    require_str_sequence,
)

template_key = "search-grid-navigation-v2"
theme = "Algorithms"
difficulties: tuple[Difficulty, ...] = ("expert",)
prompt = (
    "Input is a grid made from S, E, ., and #. Return the integer score implied by the samples "
    "for traversing that grid."
)
hint_level_1 = "Moves are only up, down, left, or right through non-wall cells."
hint_level_2 = "Think in terms of expanding reachable cells level by level from S."
hint_level_3 = "Return the fewest moves from S to E, or -1 if E cannot be reached."
contract = FunctionContract(parameter_types=("list[str]",), return_type="int")


def maze_shortest_path(grid: Sequence[str]) -> int:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    start = (-1, -1)
    end = (-1, -1)
    for row in range(rows):
        for col in range(cols):
            if grid[row][col] == "S":
                start = (row, col)
            elif grid[row][col] == "E":
                end = (row, col)

    queue: deque[tuple[int, int, int]] = deque([(start[0], start[1], 0)])
    seen = {start}
    while queue:
        row, col, dist = queue.popleft()
        if (row, col) == end:
            return dist

        for next_row, next_col in (
            (row + 1, col),
            (row - 1, col),
            (row, col + 1),
            (row, col - 1),
        ):
            if not (0 <= next_row < rows and 0 <= next_col < cols):
                continue
            if (next_row, next_col) in seen:
                continue
            if grid[next_row][next_col] == "#":
                continue
            seen.add((next_row, next_col))
            queue.append((next_row, next_col, dist + 1))

    return -1


def variable_factory(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return no_variables(rng, difficulty)


def case_factory(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    dims = {
        "easy": (5, 6),
        "medium": (7, 8),
        "hard": (9, 10),
        "expert": (11, 12),
    }
    rows, cols = dims[difficulty]
    grid = [["#" for _col in range(cols)] for _row in range(rows)]

    path = [(0, 0)]
    moves = ["D"] * (rows - 1) + ["R"] * (cols - 1)
    rng.shuffle(moves)
    row = 0
    col = 0
    for move in moves:
        if move == "D":
            row += 1
        else:
            col += 1
        path.append((row, col))

    for path_row, path_col in path:
        grid[path_row][path_col] = "."

    open_prob = {"easy": 0.40, "medium": 0.32, "hard": 0.25, "expert": 0.20}[difficulty]
    for current_row in range(rows):
        for current_col in range(cols):
            if (current_row, current_col) in path:
                continue
            if rng.random() < open_prob:
                grid[current_row][current_col] = "."

    grid[0][0] = "S"
    grid[rows - 1][cols - 1] = "E"
    lines = ["".join(chars) for chars in grid]
    return TestCase(inputs=(lines,), output=maze_shortest_path(lines))


def shared_input_factory(
    params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return no_shared_inputs(params, sample_tests)


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    del variables
    require_arity(primary_inputs, expected=1)
    grid = require_str_sequence(primary_inputs[0], label="grid")
    return maze_shortest_path(grid)
