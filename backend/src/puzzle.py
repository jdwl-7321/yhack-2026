from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pprint import pformat
import random
import string
import uuid
from typing import Any, Callable, Literal, Sequence, cast

from jinja2 import Environment, StrictUndefined, TemplateError

from constants import THEMES
from domain_types import Difficulty, JsonScalar, JsonValue

VarType = Literal["int", "float", "bool", "str", "choice"]
SamplingMode = Literal["uniform", "weighted", "fixed_list"]

_HINT_TEMPLATE_ENV = Environment(autoescape=False, undefined=StrictUndefined)


@dataclass(frozen=True, slots=True)
class VariableSpec:
    name: str
    type: VarType
    sampling: SamplingMode
    range_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TestCase:
    __test__ = False

    inputs: tuple[Any, ...]
    output: Any


@dataclass(frozen=True, slots=True)
class FunctionContract:
    parameter_types: tuple[str, ...]
    return_type: str
    parameter_names: tuple[str, ...] | None = None


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
    contract: FunctionContract
    template_key: str
    shared_inputs: tuple[Any, ...]
    fingerprint: str
    signature: str


CaseFactory = Callable[[random.Random, Difficulty, dict[str, JsonScalar]], TestCase]
VariableFactory = Callable[[random.Random, Difficulty], dict[str, JsonScalar]]
SharedInputFactory = Callable[[dict[str, JsonScalar], list[TestCase]], tuple[Any, ...]]


@dataclass(frozen=True, slots=True)
class _Template:
    key: str
    theme: str
    prompt: str
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str
    contract: FunctionContract
    case_factory: CaseFactory
    variable_factory: VariableFactory
    shared_input_factory: SharedInputFactory
    difficulties: tuple[Difficulty, ...] | None = None


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
        "function_contract": {
            "parameter_types": [
                "str",
                "int",
                "list[int]",
                "tuple[int, int]",
                "list[list[str]]",
            ],
            "return_type": "any Python expression type hint",
            "parameter_names": ["arg1", "arg2"],
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
        return "".join(rng.choice(charset) for _index in range(length))

    options = _require_values(spec.range_data)
    return rng.choice(options)


def generate_puzzle(
    *,
    theme: str,
    difficulty: Difficulty,
    seed: int,
) -> PuzzleInstance:
    normalized_theme = _normalize_theme(theme)
    rng = random.Random(seed)
    template = _select_template(normalized_theme, difficulty, rng)
    params = template.variable_factory(rng, difficulty)
    sample_tests = _build_cases(
        template,
        params,
        rng,
        difficulty,
        count=2,
        distinct_outputs=_samples_require_distinct_outputs(template.key),
    )
    shared_inputs = template.shared_input_factory(params, sample_tests)

    hidden_count = {"easy": 10, "medium": 12, "hard": 14, "expert": 16}[difficulty]
    hidden_tests = _build_cases(
        template,
        params,
        rng,
        difficulty,
        count=hidden_count,
        existing_cases=sample_tests,
    )

    fingerprint_payload = {
        "template": template.key,
        "theme": normalized_theme,
        "difficulty": difficulty,
        "variables": params,
        "contract": {
            "parameter_types": list(template.contract.parameter_types),
            "return_type": template.contract.return_type,
            "parameter_names": (
                None
                if template.contract.parameter_names is None
                else list(template.contract.parameter_names)
            ),
        },
        "shared_inputs": to_json_value(list(shared_inputs)),
    }
    fingerprint_source = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()

    signature_payload = {
        **fingerprint_payload,
        "sample_tests": [_serialize_case(case) for case in sample_tests],
        "hidden_tests": [_serialize_case(case) for case in hidden_tests],
    }
    signature_source = json.dumps(
        signature_payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()

    return PuzzleInstance(
        id=uuid.uuid4().hex[:12],
        theme=normalized_theme,
        difficulty=difficulty,
        prompt=template.prompt,
        sample_tests=sample_tests,
        hidden_tests=hidden_tests,
        hint_level_1=_render_hint_template(template.hint_level_1, params),
        hint_level_2=_render_hint_template(template.hint_level_2, params),
        hint_level_3=_render_hint_template(template.hint_level_3, params),
        variables=params,
        contract=template.contract,
        template_key=template.key,
        shared_inputs=shared_inputs,
        fingerprint=fingerprint,
        signature=signature,
    )


def generate_additional_hidden_test(
    *,
    theme: str,
    difficulty: Difficulty,
    variables: dict[str, JsonScalar],
    existing_cases: Sequence[TestCase],
    seed: int,
    template_key: str | None = None,
    retry_budget: int = 30,
) -> TestCase:
    template = (
        _template_for_key(template_key)
        if template_key is not None
        else _default_template_for_theme(_normalize_theme(theme), difficulty)
    )
    rng = random.Random(seed)
    existing_pairs = {_case_signature(case) for case in existing_cases}

    for _attempt in range(retry_budget):
        case = template.case_factory(rng, difficulty, variables)
        if _case_signature(case) not in existing_pairs:
            return case

    raise ValueError("Failed to generate a unique hidden test case")


def solution_scaffold(contract: FunctionContract) -> str:
    resolved_parameter_names = _resolve_parameter_names(contract)
    parameter_tokens = [
        f"{name}: {param_type}"
        for name, param_type in zip(
            resolved_parameter_names,
            contract.parameter_types,
            strict=True,
        )
    ]
    signature = ", ".join(parameter_tokens)
    default_expr = _default_return_expression(contract.return_type)
    return (
        f"def solution({signature}) -> {contract.return_type}:\n"
        f"    return {default_expr}\n"
    )


def format_value(value: Any) -> str:
    return pformat(value, width=96, sort_dicts=True, compact=True)


def format_case_input(inputs: Sequence[Any]) -> str:
    if len(inputs) == 1:
        return format_value(inputs[0])
    return "\n".join(
        f"arg{index + 1} = {format_value(value)}" for index, value in enumerate(inputs)
    )


def invocation_inputs(case: TestCase, shared_inputs: Sequence[Any]) -> tuple[Any, ...]:
    return (*case.inputs, *shared_inputs)


def to_json_value(value: Any) -> JsonValue:
    if isinstance(value, (str, int, float, bool)):
        return cast(JsonValue, value)
    if isinstance(value, tuple):
        return [to_json_value(item) for item in value]
    if isinstance(value, list):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, set):
        ordered = sorted(value, key=repr)
        return [to_json_value(item) for item in ordered]
    raise TypeError(f"Unsupported puzzle value type: {type(value).__name__}")


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
    max_attempts = max(60, count * 40)

    while len(cases) < count and attempts < max_attempts:
        attempts += 1
        case = template.case_factory(rng, difficulty, params)
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


def _normalize_theme(theme: str) -> str:
    normalized = theme.strip()
    if normalized in _TEMPLATES_BY_THEME:
        return normalized

    aliased = _THEME_ALIASES.get(normalized)
    if aliased is not None:
        return aliased

    prefix = normalized.split(" - ", maxsplit=1)[0].strip()
    for candidate in THEMES:
        if candidate.casefold() == prefix.casefold():
            return candidate

    raise ValueError("Unknown theme")


def _supports_difficulty(template: _Template, difficulty: Difficulty) -> bool:
    if template.difficulties is None:
        return True
    return difficulty in template.difficulties


def _samples_require_distinct_outputs(template_key: str) -> bool:
    return template_key in {"crypto-lsb-steganography-v1"}


def _select_template(
    theme: str, difficulty: Difficulty, rng: random.Random
) -> _Template:
    templates = _TEMPLATES_BY_THEME.get(theme)
    if not templates:
        raise ValueError("Theme has no registered templates")
    eligible = tuple(
        template for template in templates if _supports_difficulty(template, difficulty)
    )
    if not eligible:
        raise ValueError("Theme has no templates for this difficulty")
    return rng.choice(eligible)


def _default_template_for_theme(theme: str, difficulty: Difficulty) -> _Template:
    templates = _TEMPLATES_BY_THEME.get(theme)
    if not templates:
        raise ValueError("Theme has no registered templates")
    for template in templates:
        if _supports_difficulty(template, difficulty):
            return template
    raise ValueError("Theme has no templates for this difficulty")


def _template_for_key(template_key: str) -> _Template:
    template = _TEMPLATE_BY_KEY.get(template_key)
    if template is None:
        raise ValueError("Unknown puzzle template")
    return template


def _render_hint_template(template: str, params: dict[str, JsonScalar]) -> str:
    try:
        return _HINT_TEMPLATE_ENV.from_string(template).render(**params).strip()
    except TemplateError as exc:
        raise ValueError(f"Invalid hint template: {exc}") from exc


def _default_return_expression(return_type: str) -> str:
    defaults = {
        "str": '""',
        "int": "0",
        "float": "0.0",
        "bool": "False",
    }
    if return_type in defaults:
        return defaults[return_type]
    if return_type.startswith("tuple"):
        return "()"
    if return_type.startswith("list"):
        return "[]"
    if return_type.startswith("dict"):
        return "{}"
    return "None"


def _resolve_parameter_names(contract: FunctionContract) -> tuple[str, ...]:
    if contract.parameter_names is not None:
        if len(contract.parameter_names) != len(contract.parameter_types):
            raise ValueError(
                "Contract parameter_names length must match parameter_types"
            )
        if not all(name.isidentifier() for name in contract.parameter_names):
            raise ValueError("Contract parameter_names must be valid identifiers")
        return contract.parameter_names

    return tuple(f"arg{index + 1}" for index in range(len(contract.parameter_types)))


def _serialize_case(case: TestCase) -> dict[str, JsonValue]:
    return {
        "inputs": to_json_value(list(case.inputs)),
        "output": to_json_value(case.output),
    }


def _case_signature(case: TestCase) -> str:
    payload = _serialize_case(case)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _case_output_signature(case: TestCase) -> str:
    return json.dumps(to_json_value(case.output), sort_keys=True, separators=(",", ":"))


def _no_variables(_: random.Random, __: Difficulty) -> dict[str, JsonScalar]:
    return {}


def _no_shared_inputs(
    _params: dict[str, JsonScalar], _sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return ()


def _sample_pairs_shared_inputs(
    _params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    pairs: list[list[str]] = []
    for case in sample_tests:
        if len(case.inputs) != 1:
            raise ValueError("Expected one primary input for sample-pair context")
        input_value = case.inputs[0]
        if not isinstance(input_value, str) or not isinstance(case.output, str):
            raise ValueError("Sample-pair context requires string-to-string cases")
        pairs.append([input_value, case.output])
    return (pairs,)


def _sample_pairs_shared_scalar_inputs(
    _params: dict[str, JsonScalar], sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    pairs: list[list[JsonScalar]] = []
    for case in sample_tests:
        if len(case.inputs) != 1:
            raise ValueError("Expected one primary input for sample-pair context")
        input_value = case.inputs[0]
        if not _is_scalar(input_value) or not _is_scalar(case.output):
            raise ValueError("Sample-pair context requires scalar-to-scalar cases")
        pairs.append([cast(JsonScalar, input_value), cast(JsonScalar, case.output)])
    return (pairs,)


def _solve_xor_byte(value: int, key: int) -> int:
    return (value ^ key) & 0xFF


def _variables_xor_byte(
    rng: random.Random, _difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return {"key": rng.randint(1, 255)}


def _case_xor_byte(
    rng: random.Random, _difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    value = rng.randint(0, 255)
    key = int(params["key"])
    return TestCase(inputs=(value,), output=_solve_xor_byte(value, key))


def _shift_char(char: str, shift: int) -> str:
    if "a" <= char <= "z":
        base = ord("a")
        return chr(base + ((ord(char) - base + shift) % 26))
    if "A" <= char <= "Z":
        base = ord("A")
        return chr(base + ((ord(char) - base + shift) % 26))
    return char


def _solve_caesar(text: str, shift: int) -> str:
    return "".join(_shift_char(char, shift) for char in text)


def _variables_shift_cipher(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    shift_span = {"easy": 8, "medium": 12, "hard": 18, "expert": 25}[difficulty]
    shift = rng.randint(1, shift_span)
    if difficulty in {"hard", "expert"} and rng.random() < 0.4:
        shift *= -1
    return {"shift": shift}


def _random_text_with_letters(rng: random.Random, length: int) -> str:
    charset = string.ascii_letters + "      ,.!?-"
    chars = [rng.choice(charset) for _index in range(length)]
    if sum(1 for char in chars if char.isalpha()) < 3:
        for _index in range(3):
            chars[rng.randrange(len(chars))] = rng.choice(string.ascii_lowercase)
    text = "".join(chars).strip()
    return text or "abc"


def _case_shift_cipher(
    rng: random.Random, difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    length = {"easy": 16, "medium": 26, "hard": 40, "expert": 56}[difficulty]
    shift = int(params["shift"])
    source = _random_text_with_letters(rng, length)
    return TestCase(inputs=(source,), output=_solve_caesar(source, shift))


def _solve_substitution(text: str, source: str, target: str) -> str:
    mapping = {src: dst for src, dst in zip(source, target, strict=True)}
    return "".join(mapping.get(char, char) for char in text)


def _variables_substitution_cipher(
    rng: random.Random, difficulty: Difficulty
) -> dict[str, JsonScalar]:
    alphabet_size = {"easy": 5, "medium": 7, "hard": 9, "expert": 11}[difficulty]
    source_chars = rng.sample(list(string.ascii_lowercase), alphabet_size)
    source = "".join(source_chars)

    target_chars = source_chars[:]
    while target_chars == source_chars:
        rng.shuffle(target_chars)

    target = "".join(target_chars)
    return {"source": source, "target": target}


def _case_substitution_cipher(
    rng: random.Random, difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    source = str(params["source"])
    target = str(params["target"])
    source_chars = list(source)

    extras = {"easy": 8, "medium": 14, "hard": 22, "expert": 30}[difficulty]
    text_chars = source_chars + [rng.choice(source_chars) for _index in range(extras)]
    rng.shuffle(text_chars)
    source_text = "".join(text_chars)

    return TestCase(
        inputs=(source_text,),
        output=_solve_substitution(source_text, source, target),
    )


def _decode_lsb_ascii(values: Sequence[int]) -> str:
    if len(values) % 8 != 0:
        raise ValueError("Encoded value count must be a multiple of 8")

    chars: list[str] = []
    for start in range(0, len(values), 8):
        chunk = values[start : start + 8]
        byte = 0
        for value in chunk:
            byte = (byte << 1) | (value & 1)
        chars.append(chr(byte))
    return "".join(chars)


def _encode_word_as_lsb_values(rng: random.Random, word: str) -> list[int]:
    bits = "".join(f"{ord(char):08b}" for char in word)
    values: list[int] = []

    for bit in bits:
        value = rng.randint(0, 255)
        if bit == "1":
            value |= 1
        else:
            value &= ~1

        if rng.random() < 0.25:
            value += 256 * rng.randint(1, 3)
        values.append(value)

    return values


def _case_lsb_steganography(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    words_by_difficulty = {
        "easy": ["tree", "code", "salt", "mint", "bird", "game", "book"],
        "medium": ["cipher", "planet", "rocket", "winter", "bridge", "forest"],
        "hard": [
            "quantum",
            "network",
            "library",
            "orchard",
            "compass",
            "harvest",
        ],
        "expert": [
            "sandwich",
            "bluebird",
            "notebook",
            "elephant",
            "sunshine",
            "hardware",
        ],
    }
    word = rng.choice(words_by_difficulty[difficulty])
    encoded = _encode_word_as_lsb_values(rng, word)
    decoded = _decode_lsb_ascii(encoded)
    return TestCase(inputs=(encoded,), output=decoded)


def _two_sum_pairs(values: Sequence[int], target: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for left in range(len(values)):
        for right in range(left + 1, len(values)):
            if values[left] + values[right] == target:
                pairs.append((left, right))
    return pairs


def _case_two_sum(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    length = {"easy": 6, "medium": 8, "hard": 11, "expert": 14}[difficulty]
    span = {"easy": 20, "medium": 60, "hard": 130, "expert": 260}[difficulty]
    for _attempt in range(300):
        values = [rng.randint(-span, span) for _index in range(length)]
        first, second = sorted(rng.sample(range(length), 2))
        target = values[first] + values[second]
        pairs = _two_sum_pairs(values, target)
        if len(pairs) == 1:
            return TestCase(inputs=(values, target), output=pairs[0])
    raise ValueError("Unable to construct unique index-pair case")


def _maze_shortest_path(grid: Sequence[str]) -> int:
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


def _case_maze(
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
    return TestCase(inputs=(lines,), output=_maze_shortest_path(lines))


def _case_gcd_lcm(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    span = {"easy": 90, "medium": 260, "hard": 1500, "expert": 7000}[difficulty]
    left = rng.randint(2, span)
    right = rng.randint(2, span)
    gcd_value = math.gcd(left, right)
    lcm_value = abs(left * right) // gcd_value
    return TestCase(inputs=(left, right), output=(gcd_value, lcm_value))


def _longest_unique_substring(text: str) -> int:
    last_index: dict[str, int] = {}
    best = 0
    start = 0
    for index, char in enumerate(text):
        if char in last_index and last_index[char] >= start:
            start = last_index[char] + 1
        last_index[char] = index
        best = max(best, index - start + 1)
    return best


def _case_longest_unique(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    length = {"easy": 10, "medium": 16, "hard": 24, "expert": 36}[difficulty]
    alphabet = {
        "easy": "abcde",
        "medium": "abcdefghi",
        "hard": "abcdefghijkl",
        "expert": string.ascii_lowercase,
    }[difficulty]
    text = "".join(rng.choice(alphabet) for _index in range(length))
    return TestCase(inputs=(text,), output=_longest_unique_substring(text))


_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _is_balanced_brackets(source: str) -> bool:
    stack: list[str] = []
    for char in source:
        if char in _BRACKET_PAIRS:
            stack.append(char)
            continue
        if char in ")]}":
            if not stack:
                return False
            opener = stack.pop()
            if _BRACKET_PAIRS[opener] != char:
                return False
    return not stack


def _make_valid_bracket_text(rng: random.Random, pair_count: int) -> str:
    stack: list[str] = []
    chars: list[str] = []
    while len(chars) < pair_count * 2:
        can_open_more = len(chars) + len(stack) < pair_count * 2
        if can_open_more and (not stack or rng.random() < 0.62):
            opener = rng.choice(list(_BRACKET_PAIRS))
            stack.append(opener)
            chars.append(opener)
        else:
            opener = stack.pop()
            chars.append(_BRACKET_PAIRS[opener])
    return "".join(chars)


def _make_invalid_bracket_text(rng: random.Random, pair_count: int) -> str:
    for _attempt in range(32):
        baseline = list(_make_valid_bracket_text(rng, pair_count))
        mode = rng.choice(["swap", "drop", "append"])
        if mode == "swap" and baseline:
            index = rng.randrange(len(baseline))
            baseline[index] = rng.choice(list("()[]{}"))
        elif mode == "drop" and len(baseline) > 1:
            del baseline[rng.randrange(len(baseline))]
        else:
            baseline.append(rng.choice(list(_BRACKET_PAIRS)))

        candidate = "".join(baseline)
        if not _is_balanced_brackets(candidate):
            return candidate

    return "(" * pair_count


def _case_balanced_brackets(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    pair_count = {"easy": 4, "medium": 6, "hard": 8, "expert": 11}[difficulty]
    if rng.random() < 0.5:
        text = _make_valid_bracket_text(rng, pair_count)
    else:
        text = _make_invalid_bracket_text(rng, pair_count)
    return TestCase(inputs=(text,), output=_is_balanced_brackets(text))


def _max_non_overlapping(intervals: Sequence[tuple[int, int]]) -> int:
    ordered = sorted(intervals, key=lambda value: (value[1], value[0]))
    taken = 0
    current_end: int | None = None
    for start, end in ordered:
        if current_end is None or start >= current_end:
            taken += 1
            current_end = end
    return taken


def _case_non_overlapping_count(
    rng: random.Random, difficulty: Difficulty, _params: dict[str, JsonScalar]
) -> TestCase:
    count = {"easy": 6, "medium": 8, "hard": 11, "expert": 14}[difficulty]
    span = {"easy": 16, "medium": 30, "hard": 45, "expert": 70}[difficulty]
    width = {"easy": 5, "medium": 8, "hard": 12, "expert": 18}[difficulty]
    intervals = [
        (start, start + rng.randint(1, width))
        for start in (rng.randint(0, span) for _index in range(count))
    ]
    rng.shuffle(intervals)
    return TestCase(inputs=(intervals,), output=_max_non_overlapping(intervals))


_TEMPLATES: tuple[_Template, ...] = (
    _Template(
        key="crypto-xor-byte-inference-v1",
        theme="Cryptography",
        prompt=(
            "A deterministic 8-bit XOR mask is used across this match. "
            "`examples` contains visible [input, output] byte pairs produced with that same mask. "
            "Implement solution(value, examples) so it applies the same transformation to `value`."
        ),
        hint_level_1="Every value is an integer byte in the inclusive range 0..255.",
        hint_level_2="A single hidden mask is reused unchanged for all tests in the match.",
        hint_level_3="Infer the mask from a sample pair using output == input ^ mask, then apply that mask.",
        contract=FunctionContract(
            parameter_types=("int", "list[list[int]]"),
            return_type="int",
            parameter_names=("value", "samples"),
        ),
        case_factory=_case_xor_byte,
        variable_factory=_variables_xor_byte,
        shared_input_factory=_sample_pairs_shared_scalar_inputs,
        difficulties=("easy",),
    ),
    _Template(
        key="crypto-shift-inference-v2",
        theme="Cryptography",
        prompt=(
            "A deterministic text transformation is used across this match. "
            "`examples` contains visible [input, output] pairs generated by that same hidden rule. "
            "Implement solution(text, examples) so it applies the same rule to `text`."
        ),
        hint_level_1="Each letter is transformed independently; punctuation and spaces stay unchanged.",
        hint_level_2="One fixed alphabet rotation amount is reused for every case in the match.",
        hint_level_3="Infer that rotation from any example letter mapping, then apply it to the input text.",
        contract=FunctionContract(
            parameter_types=("str", "list[list[str]]"),
            return_type="str",
            parameter_names=("text", "samples"),
        ),
        case_factory=_case_shift_cipher,
        variable_factory=_variables_shift_cipher,
        shared_input_factory=_sample_pairs_shared_inputs,
        difficulties=("medium",),
    ),
    _Template(
        key="crypto-substitution-inference-v2",
        theme="Cryptography",
        prompt=(
            "A deterministic character substitution is used across this match. "
            "`examples` contains visible [input, output] pairs produced with the same hidden mapping. "
            "Implement solution(text, examples) so it applies that same mapping to `text`."
        ),
        hint_level_1="Each source character always maps to exactly one target character.",
        hint_level_2="The mapping is one-to-one and reused unchanged for all tests in the match.",
        hint_level_3="Build a mapping table from example characters, then translate the input text.",
        contract=FunctionContract(
            parameter_types=("str", "list[list[str]]"),
            return_type="str",
            parameter_names=("text", "samples"),
        ),
        case_factory=_case_substitution_cipher,
        variable_factory=_variables_substitution_cipher,
        shared_input_factory=_sample_pairs_shared_inputs,
        difficulties=("hard",),
    ),
    _Template(
        key="crypto-lsb-steganography-v1",
        theme="Cryptography",
        prompt=(
            "Given a list of integers, decode the hidden text value implied by the samples and return it as a string."
        ),
        hint_level_1="Each integer contributes exactly one binary digit.",
        hint_level_2="That digit is determined by whether the integer is odd or even.",
        hint_level_3="Read least-significant bits in order, group every 8 bits, and decode ASCII characters.",
        contract=FunctionContract(
            parameter_types=("list[int]",),
            return_type="str",
            parameter_names=("numbers",),
        ),
        case_factory=_case_lsb_steganography,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
        difficulties=("expert",),
    ),
    _Template(
        key="algorithms-index-pair-v2",
        theme="Algorithms",
        prompt=(
            "Given a list of integers and a target integer, return a pair of indices that follows "
            "the hidden rule shown by the samples."
        ),
        hint_level_1="The output always has two indices where the first is smaller than the second.",
        hint_level_2="Exactly one valid pair exists per case.",
        hint_level_3="Return indices i, j such that values[i] + values[j] == target.",
        contract=FunctionContract(
            parameter_types=("list[int]", "int"),
            return_type="tuple[int, int]",
        ),
        case_factory=_case_two_sum,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
    _Template(
        key="search-grid-navigation-v2",
        theme="Search",
        prompt=(
            "Input is a grid made from S, E, ., and #. Return the integer score implied by the samples "
            "for traversing that grid."
        ),
        hint_level_1="Moves are only up, down, left, or right through non-wall cells.",
        hint_level_2="Think in terms of expanding reachable cells level by level from S.",
        hint_level_3="Return the fewest moves from S to E, or -1 if E cannot be reached.",
        contract=FunctionContract(parameter_types=("list[str]",), return_type="int"),
        case_factory=_case_maze,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
    _Template(
        key="numeric-divisor-multiple-v2",
        theme="Numeric",
        prompt=(
            "Given two positive integers, return a tuple of two derived integers matching the sample pattern."
        ),
        hint_level_1="The first output value divides both inputs.",
        hint_level_2="The second output value is a shared multiple of both inputs.",
        hint_level_3="Return (gcd(a, b), lcm(a, b)).",
        contract=FunctionContract(
            parameter_types=("int", "int"),
            return_type="tuple[int, int]",
        ),
        case_factory=_case_gcd_lcm,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
    _Template(
        key="strings-window-length-v2",
        theme="Strings",
        prompt=(
            "Given a string, return the integer metric over contiguous segments that is suggested by the samples."
        ),
        hint_level_1="Repeated characters force the active segment to shift forward.",
        hint_level_2="A sliding window with last-seen positions works efficiently.",
        hint_level_3="Return the length of the longest substring with all distinct characters.",
        contract=FunctionContract(parameter_types=("str",), return_type="int"),
        case_factory=_case_longest_unique,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
    _Template(
        key="datastructures-bracket-structure-v2",
        theme="Data structures",
        prompt=(
            "Given a bracket string, return a boolean according to the structural validity rule implied by samples."
        ),
        hint_level_1="Track opening symbols and how they are closed.",
        hint_level_2="A closing bracket must match the most recent unmatched opening bracket.",
        hint_level_3="Return True only when every bracket is matched and correctly nested.",
        contract=FunctionContract(parameter_types=("str",), return_type="bool"),
        case_factory=_case_balanced_brackets,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
    _Template(
        key="greedy-interval-selection-v2",
        theme="Greedy",
        prompt=(
            "Given integer intervals, return the maximum count selected under the non-overlap rule shown by samples."
        ),
        hint_level_1="A selected interval blocks later intervals that start before it ends.",
        hint_level_2="Sorting by earliest finishing time enables the optimal strategy.",
        hint_level_3="Choose the largest set of intervals where each next start is >= previous end.",
        contract=FunctionContract(
            parameter_types=("list[tuple[int, int]]",),
            return_type="int",
        ),
        case_factory=_case_non_overlapping_count,
        variable_factory=_no_variables,
        shared_input_factory=_no_shared_inputs,
    ),
)


_TEMPLATE_BY_KEY: dict[str, _Template] = {
    template.key: template for template in _TEMPLATES
}
if len(_TEMPLATE_BY_KEY) != len(_TEMPLATES):
    raise ValueError("Puzzle template keys must be unique")


_TEMPLATES_BY_THEME: dict[str, tuple[_Template, ...]] = {
    theme: tuple(template for template in _TEMPLATES if template.theme == theme)
    for theme in THEMES
}


if set(THEMES) != set(_TEMPLATES_BY_THEME):
    raise ValueError("Theme catalog and puzzle templates are out of sync")


for theme_name, templates in _TEMPLATES_BY_THEME.items():
    if not templates:
        raise ValueError(f"Theme has no templates: {theme_name}")


_THEME_ALIASES = {
    "Cryptography - Caesar cipher": "Cryptography",
    "Cryptography - Random substitution cipher": "Cryptography",
    "Cryptography - Monoalphabetic substitution cipher": "Cryptography",
    "Cryptography - LSB steganography": "Cryptography",
    "Cryptography - XOR byte mask": "Cryptography",
    "Algorithms - Two sum indices": "Algorithms",
    "Algorithms - Merge overlapping intervals": "Algorithms",
    "Algorithms - Product of array except self": "Algorithms",
    "Search - Minimum path length in char maze": "Search",
    "Search - Knight shortest move count": "Search",
    "Numeric - GCD and LCM pair": "Numeric",
    "Numeric - Fast modular exponent": "Numeric",
    "Strings - Longest unique substring length": "Strings",
    "Data structures - Balanced brackets validator": "Data structures",
    "Greedy - Non-overlapping interval count": "Greedy",
}
