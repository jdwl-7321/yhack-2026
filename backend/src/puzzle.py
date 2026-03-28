from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import random
import uuid
from typing import Any, Callable, Literal, Sequence, cast

from constants import NOVELTY_POOL_SIZE, SIMILARITY_THRESHOLD
from domain_types import Difficulty, JsonScalar

VarType = Literal["int", "float", "bool", "str", "choice"]
SamplingMode = Literal["uniform", "weighted", "fixed_list"]


@dataclass(frozen=True, slots=True)
class VariableSpec:
    name: str
    type: VarType
    sampling: SamplingMode
    range_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TestCase:
    __test__ = False

    input_str: str
    output_str: str


@dataclass(frozen=True, slots=True)
class PuzzleInstance:
    id: str
    theme: str
    difficulty: Difficulty
    prompt: str
    sample_tests: list[TestCase]
    hidden_tests: list[TestCase]
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str
    variables: dict[str, JsonScalar]
    fingerprint: str
    signature: str


@dataclass(frozen=True, slots=True)
class _Template:
    key: str
    variable_schema: list[dict[str, Any]]
    prompt: str
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str
    solver: Callable[[str, dict[str, JsonScalar]], str]
    input_factory: Callable[[random.Random, Difficulty], str]


class NoveltyPool:
    def __init__(
        self,
        size: int = NOVELTY_POOL_SIZE,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self._entries: deque[tuple[str, str]] = deque(maxlen=size)
        self.similarity_threshold = similarity_threshold

    def accept(self, fingerprint: str, signature: str) -> bool:
        for existing_fp, existing_sig in self._entries:
            if fingerprint == existing_fp:
                return False
            if (
                SequenceMatcher(None, signature, existing_sig).ratio()
                >= self.similarity_threshold
            ):
                return False
        self._entries.append((fingerprint, signature))
        return True

    def __len__(self) -> int:
        return len(self._entries)


def generator_schema() -> dict[str, Any]:
    return {
        "variables": {
            "name": "identifier",
            "type": ["int", "float", "bool", "str", "choice"],
            "sampling": ["uniform", "weighted", "fixed_list"],
            "range": {
                "numeric": {"min": "number", "max": "number", "inclusive": "bool"},
                "string": {
                    "min_length": "int",
                    "max_length": "int",
                    "charset": "string",
                },
                "choice": {"options": ["..."]},
            },
        },
        "novelty": {
            "pool_size": NOVELTY_POOL_SIZE,
            "similarity_threshold": SIMILARITY_THRESHOLD,
        },
    }


def parse_variable_specs(raw: Sequence[dict[str, Any]] | None) -> list[VariableSpec]:
    if raw is None:
        return []

    specs: list[VariableSpec] = []
    allowed_types = {"int", "float", "bool", "str", "choice"}
    allowed_sampling = {"uniform", "weighted", "fixed_list"}

    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each variable spec must be an object")

        name = entry.get("name")
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("Variable name must be a valid identifier")

        var_type = entry.get("type")
        if var_type not in allowed_types:
            raise ValueError(f"Unsupported variable type: {var_type}")

        sampling = entry.get("sampling")
        if sampling not in allowed_sampling:
            raise ValueError(f"Unsupported sampling mode: {sampling}")

        range_data = entry.get("range")
        if not isinstance(range_data, dict):
            raise ValueError("Variable range must be an object")

        typed_var = cast(VarType, var_type)
        typed_sampling = cast(SamplingMode, sampling)
        _validate_range(typed_var, typed_sampling, range_data)

        specs.append(
            VariableSpec(
                name=name,
                type=typed_var,
                sampling=typed_sampling,
                range_data=range_data,
            )
        )

    return specs


def sample_parameters(
    specs: Sequence[VariableSpec], seed: int
) -> dict[str, JsonScalar]:
    rng = random.Random(seed)
    return {spec.name: sample_variable(spec, rng) for spec in specs}


def sample_variable(spec: VariableSpec, rng: random.Random) -> JsonScalar:
    if spec.sampling == "fixed_list":
        values = _require_values(spec.range_data)
        return rng.choice(values)

    if spec.sampling == "weighted":
        values = _require_values(spec.range_data)
        weights = spec.range_data.get("weights")
        if isinstance(weights, list) and len(weights) == len(values):
            numeric_weights = [float(value) for value in weights]
            return rng.choices(values, weights=numeric_weights, k=1)[0]
        return rng.choices(values, k=1)[0]

    if spec.type == "int":
        minimum = int(spec.range_data["min"])
        maximum = int(spec.range_data["max"])
        inclusive = bool(spec.range_data.get("inclusive", True))
        if not inclusive:
            minimum += 1
            maximum -= 1
        if minimum > maximum:
            raise ValueError(f"Range for {spec.name} is empty")
        return rng.randint(minimum, maximum)

    if spec.type == "float":
        minimum = float(spec.range_data["min"])
        maximum = float(spec.range_data["max"])
        return rng.uniform(minimum, maximum)

    if spec.type == "bool":
        options = _read_values(spec.range_data)
        if options is None:
            return rng.choice([False, True])
        return bool(rng.choice(options))

    if spec.type == "str":
        minimum = int(spec.range_data["min_length"])
        maximum = int(spec.range_data["max_length"])
        charset = str(spec.range_data["charset"])
        length = rng.randint(minimum, maximum)
        return "".join(rng.choice(charset) for _ in range(length))

    options = _require_values(spec.range_data)
    return rng.choice(options)


def generate_puzzle(
    *,
    theme: str,
    difficulty: Difficulty,
    seed: int,
    novelty_pool: NoveltyPool,
    retry_budget: int = 5,
) -> PuzzleInstance:
    for attempt in range(retry_budget):
        attempt_seed = seed + (attempt * 7919)
        rng = random.Random(attempt_seed)
        template = _template_for_theme(theme)
        specs = parse_variable_specs(template.variable_schema)
        params = sample_parameters(specs, attempt_seed)
        sample_tests = _build_cases(template, params, rng, difficulty, count=2)
        hidden_count = {"easy": 6, "medium": 8, "hard": 10, "expert": 12}[difficulty]
        hidden_tests = _build_cases(
            template, params, rng, difficulty, count=hidden_count
        )

        fingerprint_payload = {
            "template": template.key,
            "theme": theme,
            "difficulty": difficulty,
            "variables": params,
        }
        fingerprint_source = json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

        signature_payload = {
            **fingerprint_payload,
            "sample_tests": [
                {"in": case.input_str, "out": case.output_str} for case in sample_tests
            ],
            "hidden_tests": [
                {"in": case.input_str, "out": case.output_str} for case in hidden_tests
            ],
        }
        signature_source = json.dumps(
            signature_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()

        if not novelty_pool.accept(fingerprint, signature):
            continue

        return PuzzleInstance(
            id=uuid.uuid4().hex[:12],
            theme=theme,
            difficulty=difficulty,
            prompt=template.prompt,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            hint_level_1=template.hint_level_1,
            hint_level_2=template.hint_level_2,
            hint_level_3=template.hint_level_3.format(**params),
            variables=params,
            fingerprint=fingerprint,
            signature=signature,
        )

    raise ValueError("Failed novelty check after retry budget")


def _validate_range(
    var_type: VarType, sampling: SamplingMode, range_data: dict[str, Any]
) -> None:
    if sampling in {"fixed_list", "weighted"}:
        values = _require_values(range_data)
        if sampling == "weighted":
            weights = range_data.get("weights")
            if weights is not None:
                if not isinstance(weights, list) or len(weights) != len(values):
                    raise ValueError("Weighted sampling requires same-length weights")
                if not all(
                    _is_number(weight) and float(weight) > 0 for weight in weights
                ):
                    raise ValueError("Weights must be positive numbers")
        return

    if var_type in {"int", "float"}:
        minimum = range_data.get("min")
        maximum = range_data.get("max")
        if not _is_number(minimum) or not _is_number(maximum):
            raise ValueError("Numeric ranges need min/max numbers")
        minimum_num = cast(int | float, minimum)
        maximum_num = cast(int | float, maximum)
        if float(minimum_num) > float(maximum_num):
            raise ValueError("Range min cannot exceed max")
        return

    if var_type == "str":
        min_length = range_data.get("min_length")
        max_length = range_data.get("max_length")
        charset = range_data.get("charset")
        if not isinstance(min_length, int) or not isinstance(max_length, int):
            raise ValueError("String ranges need integer min_length/max_length")
        if min_length < 0 or max_length < min_length:
            raise ValueError("String length bounds are invalid")
        if not isinstance(charset, str) or not charset:
            raise ValueError("String ranges need a non-empty charset")
        return

    if var_type == "choice":
        _require_values(range_data)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_values(range_data: dict[str, Any]) -> list[JsonScalar] | None:
    raw = range_data.get("values", range_data.get("options"))
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError("values/options must be a non-empty list")
    if not all(_is_scalar(item) for item in raw):
        raise ValueError("All values/options must be scalar JSON values")
    return cast(list[JsonScalar], raw)


def _require_values(range_data: dict[str, Any]) -> list[JsonScalar]:
    values = _read_values(range_data)
    if values is None:
        raise ValueError("Sampling mode requires values/options")
    return values


def _build_cases(
    template: _Template,
    params: dict[str, JsonScalar],
    rng: random.Random,
    difficulty: Difficulty,
    count: int,
) -> list[TestCase]:
    cases: list[TestCase] = []
    for _ in range(count):
        input_str = template.input_factory(rng, difficulty)
        cases.append(
            TestCase(input_str=input_str, output_str=template.solver(input_str, params))
        )
    return cases


def _template_for_theme(theme: str) -> _Template:
    lowered = theme.lower()
    if "matrix/grid" in lowered:
        return _TEMPLATES["grid"]
    if (
        "string manipulation" in lowered
        or "parsing and tokenization" in lowered
        or "encoding/decoding" in lowered
    ):
        return _TEMPLATES["cipher"]
    return _TEMPLATES["linear"]


def _linear_solver(input_str: str, params: dict[str, JsonScalar]) -> str:
    multiplier = int(params["multiplier"])
    offset = int(params["offset"])
    values = [int(token) for token in input_str.split()] if input_str.strip() else []
    transformed = sorted((value * multiplier) + offset for value in values)
    return " ".join(str(value) for value in transformed)


def _linear_input(rng: random.Random, difficulty: Difficulty) -> str:
    count = {"easy": 5, "medium": 8, "hard": 12, "expert": 16}[difficulty]
    span = {"easy": 25, "medium": 80, "hard": 250, "expert": 600}[difficulty]
    return " ".join(str(rng.randint(-span, span)) for _ in range(count))


def _shift_char(char: str, shift: int) -> str:
    if "a" <= char <= "z":
        base = ord("a")
        return chr(base + ((ord(char) - base + shift) % 26))
    if "A" <= char <= "Z":
        base = ord("A")
        return chr(base + ((ord(char) - base + shift) % 26))
    return char


def _cipher_solver(input_str: str, params: dict[str, JsonScalar]) -> str:
    shift = int(params["shift"])
    reverse = bool(params["reverse_tokens"])
    out: list[str] = []
    for token in input_str.split():
        shifted = "".join(_shift_char(char, shift) for char in token)
        out.append(shifted[::-1] if reverse else shifted)
    return " ".join(out)


def _cipher_input(rng: random.Random, difficulty: Difficulty) -> str:
    word_count = {"easy": 4, "medium": 6, "hard": 8, "expert": 10}[difficulty]
    max_len = {"easy": 5, "medium": 7, "hard": 10, "expert": 12}[difficulty]
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    words = [
        "".join(rng.choice(alphabet) for _ in range(rng.randint(3, max_len)))
        for _ in range(word_count)
    ]
    return " ".join(words)


def _grid_solver(input_str: str, params: dict[str, JsonScalar]) -> str:
    rows = [line for line in input_str.splitlines() if line.strip()]
    matrix = [[int(value.strip()) for value in row.split(",")] for row in rows]
    if not matrix:
        return ""

    clockwise = bool(params["clockwise"])
    if clockwise:
        rotated = list(zip(*matrix[::-1]))
    else:
        rotated = list(zip(*matrix))
        rotated.reverse()

    return "\n".join(",".join(str(value) for value in row) for row in rotated)


def _grid_input(rng: random.Random, difficulty: Difficulty) -> str:
    side = {"easy": 2, "medium": 3, "hard": 4, "expert": 5}[difficulty]
    rows = [",".join(str(rng.randint(0, 99)) for _ in range(side)) for _ in range(side)]
    return "\n".join(rows)


_TEMPLATES: dict[str, _Template] = {
    "linear": _Template(
        key="linear-v1",
        variable_schema=[
            {
                "name": "multiplier",
                "type": "int",
                "sampling": "uniform",
                "range": {"min": 2, "max": 7, "inclusive": True},
            },
            {
                "name": "offset",
                "type": "int",
                "sampling": "uniform",
                "range": {"min": -9, "max": 9, "inclusive": True},
            },
        ],
        prompt=(
            "Read whitespace-separated integers. Apply a hidden linear transform to each value, "
            "then output the transformed values in ascending order separated by spaces."
        ),
        hint_level_1=(
            "The output is derived from every input number and then reordered from smallest to largest."
        ),
        hint_level_2=(
            "Every number goes through the same linear value-mapping step before the final ascending sort."
        ),
        hint_level_3="This round applies x -> (x * {multiplier}) + {offset}, then sorts ascending.",
        solver=_linear_solver,
        input_factory=_linear_input,
    ),
    "cipher": _Template(
        key="cipher-v1",
        variable_schema=[
            {
                "name": "shift",
                "type": "int",
                "sampling": "uniform",
                "range": {"min": 1, "max": 6, "inclusive": True},
            },
            {
                "name": "reverse_tokens",
                "type": "choice",
                "sampling": "fixed_list",
                "range": {"values": [True, False]},
            },
        ],
        prompt=(
            "Read lowercase words separated by spaces. Shift letters by a hidden Caesar offset. "
            "A hidden toggle may reverse each shifted token. Output transformed tokens space-separated."
        ),
        hint_level_1=(
            "Each output token comes from transforming the matching input token in place."
        ),
        hint_level_2=(
            "Letters are shifted by a consistent Caesar-style rule, and token order stays unchanged."
        ),
        hint_level_3=(
            "This round shifts letters by {shift}; reverse each transformed token only when "
            "reverse_tokens={reverse_tokens}."
        ),
        solver=_cipher_solver,
        input_factory=_cipher_input,
    ),
    "grid": _Template(
        key="grid-v1",
        variable_schema=[
            {
                "name": "clockwise",
                "type": "choice",
                "sampling": "fixed_list",
                "range": {"values": [True, False]},
            }
        ],
        prompt=(
            "Input is a square matrix with comma-separated ints per row. "
            "Rotate the matrix by 90 degrees using the hidden direction flag. "
            "Return rows in the same comma-separated format."
        ),
        hint_level_1="The output keeps the same square shape as the input matrix.",
        hint_level_2="The transformation is a quarter-turn rotation of the full matrix.",
        hint_level_3="This round rotates 90 degrees with clockwise={clockwise}.",
        solver=_grid_solver,
        input_factory=_grid_input,
    ),
}
