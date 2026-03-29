from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from pprint import pformat
import random
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence, cast
import uuid

from jinja2 import Environment, StrictUndefined, TemplateError

from constants import THEMES
from domain_types import Difficulty, JsonScalar, JsonValue

VarType = Literal["int", "float", "bool", "str", "choice"]
SamplingMode = Literal["uniform", "weighted", "fixed_list"]

_HINT_TEMPLATE_ENV = Environment(autoescape=False, undefined=StrictUndefined)
_PUZZLE_MODULE_DIR = Path(__file__).resolve().parent / "puzzles"
_PUZZLE_MODULE_SUFFIX = "_puzzle.py"


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
ExpectedOutputFactory = Callable[..., Any]
ContractFactory = Callable[[dict[str, JsonScalar]], FunctionContract]


@dataclass(frozen=True, slots=True)
class _Template:
    key: str
    theme: str
    prompt: str
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str
    contract: FunctionContract
    contract_factory: ContractFactory | None
    case_factory: CaseFactory
    variable_factory: VariableFactory
    shared_input_factory: SharedInputFactory
    expected_output_factory: ExpectedOutputFactory
    source_path: str
    difficulties: tuple[Difficulty, ...] | None = None
    distinct_sample_outputs: bool = False


@dataclass(frozen=True, slots=True)
class HardcodedPuzzleTemplate:
    template_key: str
    theme: str
    difficulty: Difficulty
    prompt: str
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str
    contract: FunctionContract


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
    return _build_puzzle_instance(
        template=template,
        theme=normalized_theme,
        difficulty=difficulty,
        rng=rng,
        prompt=template.prompt,
        hint_level_1=template.hint_level_1,
        hint_level_2=template.hint_level_2,
        hint_level_3=template.hint_level_3,
    )


def generate_puzzle_from_template(
    *,
    template_key: str,
    theme: str,
    difficulty: Difficulty,
    seed: int,
    prompt: str,
    hint_level_1: str,
    hint_level_2: str,
    hint_level_3: str,
) -> PuzzleInstance:
    normalized_theme = _normalize_theme(theme)
    template = _template_for_key(template_key)
    return _build_puzzle_instance(
        template=template,
        theme=normalized_theme,
        difficulty=difficulty,
        rng=random.Random(seed),
        prompt=prompt,
        hint_level_1=hint_level_1,
        hint_level_2=hint_level_2,
        hint_level_3=hint_level_3,
    )


def _build_puzzle_instance(
    *,
    template: _Template,
    theme: str,
    difficulty: Difficulty,
    rng: random.Random,
    prompt: str,
    hint_level_1: str,
    hint_level_2: str,
    hint_level_3: str,
) -> PuzzleInstance:
    params = template.variable_factory(rng, difficulty)
    resolved_contract = (
        template.contract_factory(params)
        if template.contract_factory is not None
        else template.contract
    )
    if not isinstance(resolved_contract, FunctionContract):
        raise ValueError("Template contract_factory must return FunctionContract")

    sample_tests = _build_cases(
        template,
        params,
        rng,
        difficulty,
        count=3,
        distinct_outputs=template.distinct_sample_outputs,
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
        "theme": theme,
        "difficulty": difficulty,
        "variables": params,
        "contract": {
            "parameter_types": list(resolved_contract.parameter_types),
            "return_type": resolved_contract.return_type,
            "parameter_names": (
                None
                if resolved_contract.parameter_names is None
                else list(resolved_contract.parameter_names)
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
        theme=theme,
        difficulty=difficulty,
        prompt=_render_text_template(prompt, params),
        sample_tests=sample_tests,
        hidden_tests=hidden_tests,
        hint_level_1=_render_text_template(hint_level_1, params),
        hint_level_2=_render_text_template(hint_level_2, params),
        hint_level_3=_render_text_template(hint_level_3, params),
        variables=params,
        contract=resolved_contract,
        template_key=template.key,
        shared_inputs=shared_inputs,
        fingerprint=fingerprint,
        signature=signature,
    )


def hardcoded_puzzle_templates() -> list[HardcodedPuzzleTemplate]:
    records: list[HardcodedPuzzleTemplate] = []
    for template in _TEMPLATES:
        if template.difficulties is None or len(template.difficulties) != 1:
            raise ValueError(
                f"Template {template.key} must declare exactly one difficulty"
            )
        records.append(
            HardcodedPuzzleTemplate(
                template_key=template.key,
                theme=template.theme,
                difficulty=template.difficulties[0],
                prompt=template.prompt,
                hint_level_1=template.hint_level_1,
                hint_level_2=template.hint_level_2,
                hint_level_3=template.hint_level_3,
                contract=template.contract,
            )
        )
    return records


def template_source_path(template_key: str) -> str:
    return _template_for_key(template_key).source_path


def template_source(template_key: str) -> str:
    path = Path(template_source_path(template_key))
    return path.read_text(encoding="utf-8")


def create_template_source(
    *, template_key: str, theme: str, difficulty: Difficulty
) -> None:
    normalized_key = _normalize_template_key(template_key)
    normalized_theme = _normalize_theme(theme)
    if difficulty not in {"easy", "medium", "hard", "expert"}:
        raise ValueError("Invalid difficulty")
    if normalized_key in _TEMPLATE_BY_KEY:
        raise ValueError("Puzzle template already exists")

    path = _candidate_template_source_path(normalized_key)
    if path.exists():
        raise ValueError("Puzzle template file already exists")

    source_code = _template_source_boilerplate(
        template_key=normalized_key,
        theme=normalized_theme,
        difficulty=difficulty,
    )
    path.write_text(source_code, encoding="utf-8")
    try:
        _refresh_template_registry()
        _template_for_key(normalized_key)
    except Exception as exc:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        _refresh_template_registry()
        raise ValueError(f"Invalid puzzle source: {exc}") from None


def delete_template_source(*, template_key: str) -> None:
    template = _template_for_key(template_key)
    path = Path(template.source_path)
    previous_source = path.read_text(encoding="utf-8")

    path.unlink()
    try:
        _refresh_template_registry()
        if template_key in _TEMPLATE_BY_KEY:
            raise ValueError("Template delete did not remove registry entry")
    except Exception as exc:
        path.write_text(previous_source, encoding="utf-8")
        _refresh_template_registry()
        raise ValueError(f"Unable to delete puzzle template: {exc}") from None


def update_template_source(*, template_key: str, source_code: str) -> None:
    template = _template_for_key(template_key)
    path = Path(template.source_path)
    if not source_code.strip():
        raise ValueError("source_code is required")

    previous_source = path.read_text(encoding="utf-8")
    path.write_text(source_code, encoding="utf-8")
    try:
        _refresh_template_registry()
        _template_for_key(template_key)
    except Exception as exc:
        path.write_text(previous_source, encoding="utf-8")
        _refresh_template_registry()
        raise ValueError(f"Invalid puzzle source: {exc}") from None


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


def expected_output_for_primary_inputs(
    *,
    template_key: str,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    template = _template_for_key(template_key)
    return template.expected_output_factory(
        variables=variables,
        primary_inputs=primary_inputs,
    )


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


def _normalize_template_key(template_key: str) -> str:
    normalized = template_key.strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
        raise ValueError(
            "template_key must be lowercase letters/numbers separated by hyphens"
        )
    return normalized


def _candidate_template_source_path(template_key: str) -> Path:
    file_name = f"{template_key.replace('-', '_')}{_PUZZLE_MODULE_SUFFIX}"
    return _PUZZLE_MODULE_DIR / file_name


def _template_source_boilerplate(
    *, template_key: str, theme: str, difficulty: Difficulty
) -> str:
    return f'''from __future__ import annotations

import random
from typing import Any, Sequence

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import require_arity, require_int_value

template_key = "{template_key}"
theme = "{theme}"
difficulties: tuple[Difficulty, ...] = ("{difficulty}",)
prompt = (
    "Given an integer value and hidden match variable `offset`, "
    "return value + offset."
)
hint_level_1 = "The input is a single integer argument."
hint_level_2 = "The offset remains the same for every test in this match."
hint_level_3 = "Use the visible examples to infer offset and add it to value."
contract = FunctionContract(
    parameter_types=("int",),
    return_type="int",
    parameter_names=("value",),
)


def variable_factory(
    rng: random.Random, _difficulty: Difficulty
) -> dict[str, JsonScalar]:
    return {{"offset": rng.randint(1, 20)}}


def case_factory(
    rng: random.Random, _difficulty: Difficulty, params: dict[str, JsonScalar]
) -> TestCase:
    value = rng.randint(-50, 50)
    offset = int(params["offset"])
    return TestCase(inputs=(value,), output=value + offset)


def shared_input_factory(
    _params: dict[str, JsonScalar], _sample_tests: list[TestCase]
) -> tuple[Any, ...]:
    return ()


def expected_output_for_primary_inputs(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    require_arity(primary_inputs, expected=1)
    value = require_int_value(primary_inputs[0], label="value")
    offset = int(variables["offset"])
    return value + offset
'''


def _render_text_template(template: str, params: dict[str, JsonScalar]) -> str:
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


def _coerce_difficulties(raw: object, *, template_key: str) -> tuple[Difficulty, ...]:
    if raw is None:
        raise ValueError(f"Template {template_key} must define difficulties")
    if not isinstance(raw, (tuple, list)) or not raw:
        raise ValueError(
            f"Template {template_key} difficulties must be a non-empty list"
        )
    parsed: list[Difficulty] = []
    for value in raw:
        if not isinstance(value, str) or value not in {
            "easy",
            "medium",
            "hard",
            "expert",
        }:
            raise ValueError(f"Template {template_key} has invalid difficulty: {value}")
        parsed.append(cast(Difficulty, value))
    return tuple(parsed)


def _import_template_module(module_name: str) -> Any:
    importlib.invalidate_caches()
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def _load_template(module_name: str, source_path: Path) -> _Template:
    module = _import_template_module(module_name)

    required_fields = (
        "template_key",
        "theme",
        "prompt",
        "hint_level_1",
        "hint_level_2",
        "hint_level_3",
        "contract",
        "difficulties",
        "case_factory",
        "variable_factory",
        "shared_input_factory",
        "expected_output_for_primary_inputs",
    )
    for field in required_fields:
        if not hasattr(module, field):
            raise ValueError(f"Template module {module_name} is missing {field}")

    template_key = getattr(module, "template_key")
    if not isinstance(template_key, str) or not template_key.strip():
        raise ValueError(f"Template module {module_name} has invalid template_key")

    theme = getattr(module, "theme")
    if not isinstance(theme, str) or theme not in THEMES:
        raise ValueError(f"Template module {module_name} has invalid theme")

    prompt = getattr(module, "prompt")
    hint_level_1 = getattr(module, "hint_level_1")
    hint_level_2 = getattr(module, "hint_level_2")
    hint_level_3 = getattr(module, "hint_level_3")
    if not all(
        isinstance(value, str)
        for value in (prompt, hint_level_1, hint_level_2, hint_level_3)
    ):
        raise ValueError(f"Template module {module_name} has invalid prompt/hints")

    contract = getattr(module, "contract")
    if not isinstance(contract, FunctionContract):
        raise ValueError(f"Template module {module_name} has invalid contract")

    difficulties = _coerce_difficulties(
        getattr(module, "difficulties"),
        template_key=template_key,
    )

    case_factory = getattr(module, "case_factory")
    variable_factory = getattr(module, "variable_factory")
    shared_input_factory = getattr(module, "shared_input_factory")
    expected_output = getattr(module, "expected_output_for_primary_inputs")
    if not all(
        callable(value)
        for value in (
            case_factory,
            variable_factory,
            shared_input_factory,
            expected_output,
        )
    ):
        raise ValueError(f"Template module {module_name} has invalid callables")

    contract_factory_attr = getattr(module, "contract_factory", None)
    if contract_factory_attr is not None and not callable(contract_factory_attr):
        raise ValueError(f"Template module {module_name} has invalid contract_factory")

    distinct_sample_outputs = bool(getattr(module, "distinct_sample_outputs", False))

    return _Template(
        key=template_key,
        theme=theme,
        prompt=prompt,
        hint_level_1=hint_level_1,
        hint_level_2=hint_level_2,
        hint_level_3=hint_level_3,
        contract=contract,
        contract_factory=cast(ContractFactory, contract_factory_attr)
        if contract_factory_attr is not None
        else None,
        case_factory=cast(CaseFactory, case_factory),
        variable_factory=cast(VariableFactory, variable_factory),
        shared_input_factory=cast(SharedInputFactory, shared_input_factory),
        expected_output_factory=cast(ExpectedOutputFactory, expected_output),
        source_path=str(source_path),
        difficulties=difficulties,
        distinct_sample_outputs=distinct_sample_outputs,
    )


def _discover_template_modules() -> list[tuple[str, Path]]:
    modules: list[tuple[str, Path]] = []
    for path in sorted(_PUZZLE_MODULE_DIR.glob(f"*{_PUZZLE_MODULE_SUFFIX}")):
        module_name = f"puzzles.{path.stem}"
        modules.append((module_name, path))
    return modules


def _refresh_template_registry() -> None:
    global _TEMPLATES
    global _TEMPLATE_BY_KEY
    global _TEMPLATES_BY_THEME

    modules = _discover_template_modules()
    if not modules:
        raise ValueError("No puzzle modules found")

    templates = tuple(
        _load_template(module_name, path) for module_name, path in modules
    )
    template_by_key = {template.key: template for template in templates}
    if len(template_by_key) != len(templates):
        raise ValueError("Puzzle template keys must be unique")

    templates_by_theme = {
        theme: tuple(template for template in templates if template.theme == theme)
        for theme in THEMES
    }
    if set(THEMES) != set(templates_by_theme):
        raise ValueError("Theme catalog and puzzle templates are out of sync")
    for theme_name, theme_templates in templates_by_theme.items():
        if not theme_templates:
            raise ValueError(f"Theme has no templates: {theme_name}")

    _TEMPLATES = templates
    _TEMPLATE_BY_KEY = template_by_key
    _TEMPLATES_BY_THEME = templates_by_theme


_TEMPLATES: tuple[_Template, ...] = ()
_TEMPLATE_BY_KEY: dict[str, _Template] = {}
_TEMPLATES_BY_THEME: dict[str, tuple[_Template, ...]] = {}

_refresh_template_registry()


_THEME_ALIASES = {
    "Cryptography - Caesar cipher": "Cryptography",
    "Cryptography - Random substitution cipher": "Cryptography",
    "Cryptography - Monoalphabetic substitution cipher": "Cryptography",
    "Cryptography - LSB steganography": "Cryptography",
    "Cryptography - XOR byte mask": "Cryptography",
    "Algorithms - Two sum indices": "Algorithms",
    "Algorithms - Merge overlapping intervals": "Algorithms",
    "Algorithms - Product of array except self": "Algorithms",
    "Search - Minimum path length in char maze": "Algorithms",
    "Search - Knight shortest move count": "Algorithms",
    "Strings - Longest unique substring length": "Algorithms",
    "Data structures - Balanced brackets validator": "Algorithms",
    "Greedy - Non-overlapping interval count": "Algorithms",
    "Numeric - GCD and LCM pair": "Numeric",
    "Numeric - GCD": "Numeric",
    "Numeric - LCM": "Numeric",
    "Numeric - Prime numbers": "Numeric",
    "Numeric - Add number and reverse": "Numeric",
    "Numeric - Total number of factors": "Numeric",
    "Numeric - AX plus B linear transform": "Numeric",
    "Numeric - Fast modular exponent": "Numeric",
}
