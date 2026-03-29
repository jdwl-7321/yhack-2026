from __future__ import annotations

from dataclasses import dataclass
import json
import os
import random
import string
from typing import Any, Literal, Sequence, cast
from urllib import error as urllib_error
from urllib import request as urllib_request

from domain_types import Difficulty, JsonScalar
from puzzle import FunctionContract, TestCase
from puzzles.common import (
    require_arity,
    require_int_sequence,
    require_int_value,
    require_str_value,
    sample_pairs_shared_inputs,
    sample_pairs_shared_json_inputs,
    sample_pairs_shared_scalar_inputs,
)

_NOUS_DEFAULT_URL = "https://inference-api.nousresearch.com/v1/chat/completions"
_NOUS_DEFAULT_MODEL = "Hermes-3-Llama-3.1-70B"
_GENERAL_THEMES = ("Cryptography", "Numeric", "Algorithms")

Operation = Literal[
    "chunk_reverse",
    "alternating_shift",
    "rail_fence_encode",
    "vigenere_keyword",
    "popcount_affine",
    "alternating_digit_fold",
    "digit_square_sum_mod",
    "nearest_prime_gap",
    "pairwise_diff_checksum",
    "rotate_integer_csv",
    "peak_count",
    "max_subarray_sum",
]

Kind = Literal["str->str", "int->int", "list->int", "list->list"]


@dataclass(frozen=True, slots=True)
class _AiCopy:
    operation: str
    prompt: str
    hint_level_1: str
    hint_level_2: str
    hint_level_3: str


_THEME_DIFFICULTY_OPERATIONS: dict[tuple[str, Difficulty], tuple[Operation, ...]] = {
    ("Cryptography", "easy"): ("chunk_reverse", "alternating_shift"),
    (
        "Cryptography",
        "medium",
    ): ("chunk_reverse", "alternating_shift", "rail_fence_encode"),
    ("Cryptography", "hard"): (
        "alternating_shift",
        "rail_fence_encode",
        "vigenere_keyword",
    ),
    ("Cryptography", "expert"): (
        "rail_fence_encode",
        "vigenere_keyword",
        "alternating_shift",
    ),
    ("Numeric", "easy"): ("popcount_affine", "alternating_digit_fold"),
    (
        "Numeric",
        "medium",
    ): ("popcount_affine", "alternating_digit_fold", "digit_square_sum_mod"),
    ("Numeric", "hard"): (
        "popcount_affine",
        "digit_square_sum_mod",
        "nearest_prime_gap",
    ),
    ("Numeric", "expert"): (
        "digit_square_sum_mod",
        "nearest_prime_gap",
        "popcount_affine",
    ),
    ("Algorithms", "easy"): ("pairwise_diff_checksum", "rotate_integer_csv"),
    ("Algorithms", "medium"): (
        "pairwise_diff_checksum",
        "rotate_integer_csv",
        "peak_count",
    ),
    ("Algorithms", "hard"): (
        "rotate_integer_csv",
        "max_subarray_sum",
        "peak_count",
    ),
    ("Algorithms", "expert"): (
        "max_subarray_sum",
        "peak_count",
        "rotate_integer_csv",
    ),
}

_OPERATION_KIND: dict[Operation, Kind] = {
    "chunk_reverse": "str->str",
    "alternating_shift": "str->str",
    "rail_fence_encode": "str->str",
    "vigenere_keyword": "str->str",
    "popcount_affine": "int->int",
    "alternating_digit_fold": "int->int",
    "digit_square_sum_mod": "int->int",
    "nearest_prime_gap": "int->int",
    "pairwise_diff_checksum": "list->int",
    "rotate_integer_csv": "list->list",
    "peak_count": "list->int",
    "max_subarray_sum": "list->int",
}

_OPERATION_DESCRIPTIONS: dict[Operation, str] = {
    "chunk_reverse": "Split text into fixed-size chunks and reverse each chunk.",
    "alternating_shift": "Shift letters using two alternating offsets by letter position.",
    "rail_fence_encode": "Apply rail-fence transposition using a hidden rail count.",
    "vigenere_keyword": "Shift letters by a repeating hidden keyword.",
    "popcount_affine": "Return a*bitcount(abs(n)) + b for integer arg1.",
    "alternating_digit_fold": "Fold digits of abs(n) with alternating + / - signs, then add offset.",
    "digit_square_sum_mod": "Return (sum(square(digits(abs(n)))) + bias) mod m.",
    "nearest_prime_gap": "Return the distance from n to the nearest prime number.",
    "pairwise_diff_checksum": "Return sum(abs(arr[i] - arr[i-1])) over a list of integers.",
    "rotate_integer_csv": "Rotate a list of integers left by hidden k.",
    "peak_count": "Count strict local peaks in a list of integers.",
    "max_subarray_sum": "Return the maximum contiguous subarray sum.",
}

_OPERATION_HINTS: dict[Operation, tuple[str, str, str]] = {
    "chunk_reverse": (
        "arg1 is text transformed block-by-block.",
        "A single chunk size is reused for all cases in the match.",
        "Infer chunk size from samples, then reverse each chunk independently.",
    ),
    "alternating_shift": (
        "Only letters shift; punctuation and spaces stay unchanged.",
        "Two shifts alternate as you move across letters.",
        "Infer both shifts from samples and apply by letter index parity.",
    ),
    "rail_fence_encode": (
        "Characters are written in a zig-zag rail pattern.",
        "Rail count is fixed for the entire match.",
        "Infer rails from samples and read row-by-row to encode.",
    ),
    "vigenere_keyword": (
        "Only alphabetic characters are shifted; case is preserved.",
        "A keyword repeats over letters and controls each shift.",
        "Infer keyword shifts from samples and repeat across arg1.",
    ),
    "popcount_affine": (
        "arg1 is an integer and abs(arg1) is used.",
        "Compute bitcount(abs(n)) first, then apply a fixed linear transform.",
        "Infer a and b from samples and return a*bitcount + b.",
    ),
    "alternating_digit_fold": (
        "arg1 is an integer and digit order matters.",
        "Digits are combined with alternating + / - signs.",
        "Compute that fold on abs(n) and add one fixed offset.",
    ),
    "digit_square_sum_mod": (
        "arg1 is an integer and uses digits of abs(arg1).",
        "Square each digit, sum them, then apply fixed bias and modulus.",
        "Infer bias and modulus from samples and apply to arg1.",
    ),
    "nearest_prime_gap": (
        "Output is non-negative and based on nearby primes.",
        "Measure minimum distance between n and any prime.",
        "Check upward/downward from n until you hit a prime.",
    ),
    "pairwise_diff_checksum": (
        "arg1 is a list of integers.",
        "Only adjacent differences are used.",
        "Sum absolute adjacent diffs across the list.",
    ),
    "rotate_integer_csv": (
        "arg1 is a list of integers and output is a list of integers.",
        "A fixed left-rotation amount k is reused for this match.",
        "Infer k from samples, rotate left, return the new list.",
    ),
    "peak_count": (
        "arg1 is a list of integers.",
        "A peak is strictly greater than immediate neighbor(s).",
        "Count edge/internal peaks with strict comparisons.",
    ),
    "max_subarray_sum": (
        "arg1 is a list of integers and output is one integer.",
        "The result is the best sum over all contiguous subarrays.",
        "Use a running-best scan (Kadane style) to compute efficiently.",
    ),
}


def ai_variable_factory(
    rng: random.Random,
    difficulty: Difficulty,
) -> dict[str, JsonScalar]:
    general_theme = rng.choice(_GENERAL_THEMES)
    allowed_operations = _THEME_DIFFICULTY_OPERATIONS[(general_theme, difficulty)]
    fallback_operation = rng.choice(allowed_operations)

    ai_copy = _build_ai_copy(
        difficulty=difficulty,
        general_theme=general_theme,
        allowed_operations=allowed_operations,
        fallback_operation=fallback_operation,
    )
    operation = (
        cast_operation(ai_copy.operation)
        if ai_copy.operation in allowed_operations
        else fallback_operation
    )

    prompt, hint_1, hint_2, hint_3 = _fallback_copy(
        difficulty=difficulty,
        general_theme=general_theme,
        operation=operation,
    )
    prompt = _normalize_copy_text(ai_copy.prompt, fallback=prompt, max_len=900)
    if "samples" not in prompt:
        prompt = f"{prompt} `samples` contains visible examples."
    hint_1 = _normalize_copy_text(ai_copy.hint_level_1, fallback=hint_1, max_len=260)
    hint_2 = _normalize_copy_text(ai_copy.hint_level_2, fallback=hint_2, max_len=260)
    hint_3 = _normalize_copy_text(ai_copy.hint_level_3, fallback=hint_3, max_len=260)

    operation_params = _operation_parameters(operation, difficulty, rng)
    topic_key = f"{general_theme}:{operation}"
    return {
        "general_theme": general_theme,
        "operation": operation,
        "topic_key": topic_key,
        "operation_params_json": json.dumps(
            operation_params,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "prompt_text": prompt,
        "hint_level_1_text": hint_1,
        "hint_level_2_text": hint_2,
        "hint_level_3_text": hint_3,
    }


def ai_contract_factory(variables: dict[str, JsonScalar]) -> FunctionContract:
    operation = _operation_name(variables)
    kind = _OPERATION_KIND[operation]

    if kind == "str->str":
        return FunctionContract(
            parameter_types=("str", "list[tuple[str, str]]"),
            return_type="str",
            parameter_names=("arg1", "samples"),
        )

    if kind == "int->int":
        return FunctionContract(
            parameter_types=("int", "list[list[int]]"),
            return_type="int",
            parameter_names=("arg1", "samples"),
        )

    if kind == "list->int":
        return FunctionContract(
            parameter_types=("list[int]", "list[tuple[list[int], int]]"),
            return_type="int",
            parameter_names=("arg1", "samples"),
        )

    return FunctionContract(
        parameter_types=("list[int]", "list[tuple[list[int], list[int]]]"),
        return_type="list[int]",
        parameter_names=("arg1", "samples"),
    )


def ai_shared_input_factory(
    params: dict[str, JsonScalar],
    sample_tests: list[TestCase],
) -> tuple[Any, ...]:
    operation = _operation_name(params)
    kind = _OPERATION_KIND[operation]
    if kind == "str->str":
        return sample_pairs_shared_inputs(params, sample_tests)
    if kind == "int->int":
        return sample_pairs_shared_scalar_inputs(params, sample_tests)
    return sample_pairs_shared_json_inputs(params, sample_tests)


def ai_case_factory(
    rng: random.Random,
    difficulty: Difficulty,
    params: dict[str, JsonScalar],
) -> TestCase:
    operation = _operation_name(params)
    operation_params = _operation_params(params)
    arg1 = _random_input_for_operation(
        operation=operation,
        difficulty=difficulty,
        operation_params=operation_params,
        rng=rng,
    )
    return TestCase(
        inputs=(arg1,),
        output=_apply_operation(
            operation=operation,
            arg1=arg1,
            operation_params=operation_params,
        ),
    )


def ai_expected_output(
    *,
    variables: dict[str, JsonScalar],
    primary_inputs: Sequence[Any],
) -> Any:
    require_arity(primary_inputs, expected=1)
    operation = _operation_name(variables)
    return _apply_operation(
        operation=operation,
        arg1=primary_inputs[0],
        operation_params=_operation_params(variables),
    )


def cast_operation(value: str) -> Operation:
    return cast(Operation, value)


def _operation_name(variables: dict[str, JsonScalar]) -> Operation:
    value = variables.get("operation")
    if not isinstance(value, str) or value not in _OPERATION_KIND:
        raise ValueError("Invalid AI operation")
    return cast_operation(value)


def _operation_params(variables: dict[str, JsonScalar]) -> dict[str, Any]:
    raw = variables.get("operation_params_json")
    if not isinstance(raw, str) or not raw:
        raise ValueError("Missing AI operation params")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("Invalid AI operation params") from None

    if not isinstance(parsed, dict):
        raise ValueError("Invalid AI operation params")
    return parsed


def _apply_operation(
    *,
    operation: Operation,
    arg1: Any,
    operation_params: dict[str, Any],
) -> Any:
    if operation == "chunk_reverse":
        text = require_str_value(arg1, label="arg1")
        size = int(operation_params.get("size", 2))
        if size <= 0:
            raise ValueError("size must be positive")
        chunks = [text[index : index + size] for index in range(0, len(text), size)]
        return "".join(chunk[::-1] for chunk in chunks)

    if operation == "alternating_shift":
        text = require_str_value(arg1, label="arg1")
        even_shift = int(operation_params.get("even_shift", 1))
        odd_shift = int(operation_params.get("odd_shift", 2))
        return _alternating_shift(text, even_shift=even_shift, odd_shift=odd_shift)

    if operation == "rail_fence_encode":
        text = require_str_value(arg1, label="arg1")
        rails = int(operation_params.get("rails", 2))
        return _rail_fence_encode(text, rails=rails)

    if operation == "vigenere_keyword":
        text = require_str_value(arg1, label="arg1")
        keyword = str(operation_params.get("keyword", "abc"))
        return _vigenere_encode(text, keyword=keyword)

    if operation == "popcount_affine":
        value = _require_int_input(arg1)
        multiplier = int(operation_params.get("multiplier", 1))
        bias = int(operation_params.get("bias", 0))
        return multiplier * abs(value).bit_count() + bias

    if operation == "alternating_digit_fold":
        value = _require_int_input(arg1)
        offset = int(operation_params.get("offset", 0))
        digits = [int(char) for char in str(abs(value))]
        folded = sum(
            digit if index % 2 == 0 else -digit for index, digit in enumerate(digits)
        )
        return folded + offset

    if operation == "digit_square_sum_mod":
        value = _require_int_input(arg1)
        modulus = int(operation_params.get("modulus", 31))
        bias = int(operation_params.get("bias", 0))
        if modulus <= 1:
            raise ValueError("modulus must be greater than 1")
        score = sum(int(char) ** 2 for char in str(abs(value)))
        return (score + bias) % modulus

    if operation == "nearest_prime_gap":
        value = abs(_require_int_input(arg1))
        return _nearest_prime_gap(value)

    if operation == "pairwise_diff_checksum":
        sequence = _require_list_input(arg1)
        return sum(
            abs(sequence[index] - sequence[index - 1])
            for index in range(1, len(sequence))
        )

    if operation == "rotate_integer_csv":
        sequence = _require_list_input(arg1)
        left_k = int(operation_params.get("left_k", 1))
        offset = left_k % len(sequence)
        return sequence[offset:] + sequence[:offset]

    if operation == "peak_count":
        sequence = _require_list_input(arg1)
        peaks = 0
        for index, value in enumerate(sequence):
            left_ok = index == 0 or value > sequence[index - 1]
            right_ok = index == len(sequence) - 1 or value > sequence[index + 1]
            if left_ok and right_ok:
                peaks += 1
        return peaks

    sequence = _require_list_input(arg1)
    best = sequence[0]
    running = sequence[0]
    for value in sequence[1:]:
        running = max(value, running + value)
        best = max(best, running)
    return best


def _require_int_input(value: Any) -> int:
    return require_int_value(value, label="arg1")


def _require_list_input(value: Any) -> list[int]:
    sequence = require_int_sequence(value, label="arg1")
    if len(sequence) < 2:
        raise ValueError("arg1 list must contain at least two integers")
    return sequence


def _shift_ascii_letter(char: str, shift: int) -> str:
    if "a" <= char <= "z":
        base = ord("a")
        return chr(base + ((ord(char) - base + shift) % 26))
    if "A" <= char <= "Z":
        base = ord("A")
        return chr(base + ((ord(char) - base + shift) % 26))
    return char


def _alternating_shift(text: str, *, even_shift: int, odd_shift: int) -> str:
    chars: list[str] = []
    letter_index = 0
    for char in text:
        if char.isalpha() and char.isascii():
            shift = even_shift if letter_index % 2 == 0 else odd_shift
            chars.append(_shift_ascii_letter(char, shift))
            letter_index += 1
            continue
        chars.append(char)
    return "".join(chars)


def _rail_fence_encode(text: str, *, rails: int) -> str:
    if rails <= 1 or len(text) <= 2:
        return text

    rows = ["" for _index in range(rails)]
    row = 0
    direction = 1
    for char in text:
        rows[row] += char
        if row == 0:
            direction = 1
        elif row == rails - 1:
            direction = -1
        row += direction
    return "".join(rows)


def _vigenere_encode(text: str, *, keyword: str) -> str:
    normalized_key = [
        ord(char.lower()) - ord("a")
        for char in keyword
        if char.isalpha() and char.isascii()
    ]
    if not normalized_key:
        return text

    key_index = 0
    encoded: list[str] = []
    for char in text:
        if char.isalpha() and char.isascii():
            shift = normalized_key[key_index % len(normalized_key)]
            encoded.append(_shift_ascii_letter(char, shift))
            key_index += 1
            continue
        encoded.append(char)
    return "".join(encoded)


def _nearest_prime_gap(value: int) -> int:
    if value <= 2:
        return 0 if value == 2 else 1
    if _is_prime(value):
        return 0

    lower = value - 1
    upper = value + 1
    while True:
        if lower >= 2 and _is_prime(lower):
            return value - lower
        if _is_prime(upper):
            return upper - value
        lower -= 1
        upper += 1


def _is_prime(candidate: int) -> bool:
    if candidate < 2:
        return False
    if candidate % 2 == 0:
        return candidate == 2
    divisor = 3
    while divisor * divisor <= candidate:
        if candidate % divisor == 0:
            return False
        divisor += 2
    return True


def _random_input_for_operation(
    *,
    operation: Operation,
    difficulty: Difficulty,
    operation_params: dict[str, Any],
    rng: random.Random,
) -> Any:
    kind = _OPERATION_KIND[operation]
    if kind == "str->str":
        min_len, max_len = {
            "easy": (8, 16),
            "medium": (14, 24),
            "hard": (22, 34),
            "expert": (30, 48),
        }[difficulty]
        return _random_text(rng, min_len=min_len, max_len=max_len)

    if kind == "int->int":
        lower, upper = {
            "easy": (-4_000, 4_000),
            "medium": (-80_000, 80_000),
            "hard": (-600_000, 600_000),
            "expert": (-2_500_000, 2_500_000),
        }[difficulty]
        return rng.randint(lower, upper)

    length = {"easy": 5, "medium": 7, "hard": 9, "expert": 12}[difficulty]
    if operation == "rotate_integer_csv":
        left_k = int(operation_params.get("left_k", 1))
        length = max(length, left_k + 2)
    return [rng.randint(-45, 45) for _index in range(length)]


def _random_text(rng: random.Random, *, min_len: int, max_len: int) -> str:
    charset = string.ascii_letters + "      ,.!?-"
    length = rng.randint(min_len, max_len)
    chars = [rng.choice(charset) for _index in range(length)]
    if sum(1 for char in chars if char.isalpha()) < 4:
        for _index in range(4):
            chars[rng.randrange(len(chars))] = rng.choice(string.ascii_lowercase)
    return "".join(chars).strip() or "signal"


def _random_keyword(rng: random.Random, *, min_len: int, max_len: int) -> str:
    length = rng.randint(min_len, max_len)
    return "".join(rng.choice(string.ascii_lowercase) for _index in range(length))


def _operation_parameters(
    operation: Operation,
    difficulty: Difficulty,
    rng: random.Random,
) -> dict[str, int | str]:
    if operation == "chunk_reverse":
        return {
            "size": rng.randint(
                2,
                {"easy": 3, "medium": 4, "hard": 5, "expert": 6}[difficulty],
            )
        }

    if operation == "alternating_shift":
        cap = {"easy": 5, "medium": 10, "hard": 14, "expert": 20}[difficulty]
        even_shift = rng.randint(1, cap)
        odd_shift = rng.randint(1, cap)
        if difficulty in {"hard", "expert"} and rng.random() < 0.35:
            odd_shift *= -1
        return {"even_shift": even_shift, "odd_shift": odd_shift}

    if operation == "rail_fence_encode":
        return {
            "rails": rng.randint(
                2,
                {"easy": 3, "medium": 4, "hard": 5, "expert": 6}[difficulty],
            )
        }

    if operation == "vigenere_keyword":
        return {
            "keyword": _random_keyword(
                rng,
                min_len=3,
                max_len={"easy": 4, "medium": 5, "hard": 6, "expert": 7}[difficulty],
            )
        }

    if operation == "popcount_affine":
        return {
            "multiplier": rng.randint(
                1,
                {"easy": 3, "medium": 4, "hard": 6, "expert": 8}[difficulty],
            ),
            "bias": rng.randint(
                -6,
                {"easy": 18, "medium": 30, "hard": 55, "expert": 90}[difficulty],
            ),
        }

    if operation == "alternating_digit_fold":
        return {
            "offset": rng.randint(
                -20,
                {"easy": 20, "medium": 40, "hard": 70, "expert": 110}[difficulty],
            )
        }

    if operation == "digit_square_sum_mod":
        return {
            "modulus": rng.randint(
                {"easy": 11, "medium": 23, "hard": 41, "expert": 73}[difficulty],
                {"easy": 23, "medium": 47, "hard": 97, "expert": 211}[difficulty],
            ),
            "bias": rng.randint(
                0,
                {"easy": 12, "medium": 40, "hard": 80, "expert": 150}[difficulty],
            ),
        }

    if operation == "rotate_integer_csv":
        return {
            "left_k": rng.randint(
                1,
                {"easy": 2, "medium": 3, "hard": 4, "expert": 5}[difficulty],
            )
        }

    return {}


def _build_ai_copy(
    *,
    difficulty: Difficulty,
    general_theme: str,
    allowed_operations: Sequence[Operation],
    fallback_operation: Operation,
) -> _AiCopy:
    fallback_prompt, fallback_hint_1, fallback_hint_2, fallback_hint_3 = _fallback_copy(
        difficulty=difficulty,
        general_theme=general_theme,
        operation=fallback_operation,
    )
    fallback = _AiCopy(
        operation=fallback_operation,
        prompt=fallback_prompt,
        hint_level_1=fallback_hint_1,
        hint_level_2=fallback_hint_2,
        hint_level_3=fallback_hint_3,
    )

    model_copy = _fetch_nous_copy(
        difficulty=difficulty,
        general_theme=general_theme,
        allowed_operations=allowed_operations,
    )
    if model_copy is None:
        return fallback

    return _AiCopy(
        operation=(
            model_copy.operation
            if model_copy.operation in allowed_operations
            else fallback.operation
        ),
        prompt=model_copy.prompt or fallback.prompt,
        hint_level_1=model_copy.hint_level_1 or fallback.hint_level_1,
        hint_level_2=model_copy.hint_level_2 or fallback.hint_level_2,
        hint_level_3=model_copy.hint_level_3 or fallback.hint_level_3,
    )


def _fallback_copy(
    *,
    difficulty: Difficulty,
    general_theme: str,
    operation: Operation,
) -> tuple[str, str, str, str]:
    kind = _OPERATION_KIND[operation]
    if kind == "str->str":
        typing_copy = "`arg1` is a string and your function returns a string"
    elif kind == "int->int":
        typing_copy = "`arg1` is an integer and your function returns an integer"
    elif kind == "list->int":
        typing_copy = (
            "`arg1` is a list of integers and your function returns an integer"
        )
    else:
        typing_copy = (
            "`arg1` is a list of integers and your function returns a list of integers"
        )

    prompt = (
        f"AI challenge ({general_theme}, {difficulty}). "
        f"In this match, {typing_copy}. "
        "`samples` contains visible (input, output) examples generated by one hidden deterministic rule. "
        "Implement `solution(arg1, samples)` to infer and apply that same rule to new inputs. "
        f"Rule family: {_OPERATION_DESCRIPTIONS[operation]}"
    )
    hint_1, hint_2, hint_3 = _OPERATION_HINTS[operation]
    return prompt, hint_1, hint_2, hint_3


def _normalize_copy_text(value: str, *, fallback: str, max_len: int) -> str:
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "..."
    return cleaned


def _fetch_nous_copy(
    *,
    difficulty: Difficulty,
    general_theme: str,
    allowed_operations: Sequence[Operation],
) -> _AiCopy | None:
    api_key = os.environ.get("NOUS_API_KEY", "").strip()
    if not api_key:
        return None

    url = os.environ.get("NOUS_API_URL", _NOUS_DEFAULT_URL).strip()
    if not url:
        return None

    model = (
        os.environ.get("NOUS_MODEL", _NOUS_DEFAULT_MODEL).strip() or _NOUS_DEFAULT_MODEL
    )
    timeout = _timeout_seconds()

    payload = {
        "model": model,
        "temperature": 0.35,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You create novel but fair programming puzzle copy. "
                    "Return valid JSON only and keep the puzzle solvable from visible examples."
                ),
            },
            {
                "role": "user",
                "content": _nous_user_prompt(
                    difficulty=difficulty,
                    general_theme=general_theme,
                    allowed_operations=allowed_operations,
                ),
            },
        ],
    }

    request_body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode("utf-8")
    except (urllib_error.URLError, TimeoutError, ValueError):
        return None

    try:
        parsed_response = json.loads(raw_response)
    except json.JSONDecodeError:
        return None

    message = _extract_chat_content(parsed_response)
    if message is None:
        return None

    parsed_copy = _parse_nous_copy_json(message)
    if parsed_copy is None:
        return None

    operation_raw = parsed_copy.get("operation")
    prompt_raw = parsed_copy.get("prompt")
    hint_1_raw = parsed_copy.get("hint_level_1")
    hint_2_raw = parsed_copy.get("hint_level_2")
    hint_3_raw = parsed_copy.get("hint_level_3")
    if not isinstance(operation_raw, str):
        return None
    if not isinstance(prompt_raw, str):
        return None
    if not isinstance(hint_1_raw, str):
        return None
    if not isinstance(hint_2_raw, str):
        return None
    if not isinstance(hint_3_raw, str):
        return None

    return _AiCopy(
        operation=operation_raw,
        prompt=prompt_raw,
        hint_level_1=hint_1_raw,
        hint_level_2=hint_2_raw,
        hint_level_3=hint_3_raw,
    )


def _timeout_seconds() -> float:
    raw = os.environ.get("NOUS_API_TIMEOUT_SECONDS", "8")
    try:
        timeout = float(raw)
    except ValueError:
        return 8.0
    return min(max(timeout, 1.0), 20.0)


def _nous_user_prompt(
    *,
    difficulty: Difficulty,
    general_theme: str,
    allowed_operations: Sequence[Operation],
) -> str:
    operation_lines = "\n".join(
        f"- {operation}: {_OPERATION_DESCRIPTIONS[operation]}"
        for operation in allowed_operations
    )
    return (
        "Create one puzzle copy pack for a coding duel match.\n"
        f"General theme: {general_theme}\n"
        f"Difficulty: {difficulty}\n"
        "The backend already generates all input/output data from one allowed operation.\n"
        "Choose exactly one allowed operation and write copy that is novel, interesting, and solvable.\n"
        "Allowed operations:\n"
        f"{operation_lines}\n\n"
        "Output strict JSON only with this schema:\n"
        "{\n"
        '  "operation": "<one allowed operation>",\n'
        '  "prompt": "<80-150 words, mention solution(arg1, samples) and that samples are visible examples>",\n'
        '  "hint_level_1": "<short practical hint>",\n'
        '  "hint_level_2": "<more concrete hint>",\n'
        '  "hint_level_3": "<strong hint, still not full direct solution>"\n'
        "}\n"
        "Hard constraints:\n"
        "- Do not use classic repeated puzzle tropes like Caesar cipher, monoalphabetic substitution, two-sum, LIS, GCD, or LCM.\n"
        "- Keep difficulty-appropriate and not impossible.\n"
        "- Keep typing natural for the operation (string/int/list[int]).\n"
        "- No markdown fences and no extra keys."
    )


def _extract_chat_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first = choices[0]
    if not isinstance(first, dict):
        return None

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            if chunks:
                return "\n".join(chunks)

    fallback = first.get("text")
    if isinstance(fallback, str):
        return fallback
    return None


def _parse_nous_copy_json(raw: str) -> dict[str, Any] | None:
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = [
            line
            for line in candidate.splitlines()
            if not line.strip().startswith("```")
        ]
        candidate = "\n".join(lines).strip()

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        return None

    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
