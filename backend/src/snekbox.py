from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, request

DEFAULT_SNEKBOX_URL = "http://127.0.0.1:8060/eval"
LOCAL_SNEKBOX_URL = "local://"
_HTTP_TIMEOUT_BUFFER_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class SnekboxExecutionResult:
    stdout: str
    returncode: int


def execute_python(code: str, *, timeout_seconds: float) -> SnekboxExecutionResult:
    url = os.environ.get("YHACK_SNEKBOX_URL", DEFAULT_SNEKBOX_URL).strip()
    if not url:
        url = DEFAULT_SNEKBOX_URL

    if url == LOCAL_SNEKBOX_URL:
        return _execute_locally(code=code, timeout_seconds=timeout_seconds)

    return _execute_via_http(url=url, code=code, timeout_seconds=timeout_seconds)


def _execute_locally(code: str, *, timeout_seconds: float) -> SnekboxExecutionResult:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            check=False,
            text=True,
            timeout=max(0.1, timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Sandbox request timed out after {timeout_seconds:.2f}s"
        ) from exc

    combined_stdout = f"{completed.stdout}{completed.stderr}"
    return SnekboxExecutionResult(
        stdout=combined_stdout,
        returncode=int(completed.returncode),
    )


def _execute_via_http(
    *,
    url: str,
    code: str,
    timeout_seconds: float,
) -> SnekboxExecutionResult:
    payload: dict[str, Any] = {"input": code}
    executable_path = os.environ.get("YHACK_SNEKBOX_EXECUTABLE_PATH", "").strip()
    if executable_path:
        payload["executable_path"] = executable_path

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(
            req,
            timeout=max(0.1, timeout_seconds + _HTTP_TIMEOUT_BUFFER_SECONDS),
        ) as response:
            raw = response.read().decode("utf-8")
            status = response.getcode()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(
            f"Snekbox request failed with HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except error.URLError as exc:
        raise ValueError(
            "Unable to reach Snekbox. Set YHACK_SNEKBOX_URL to a running "
            "Snekbox /eval endpoint."
        ) from exc
    except TimeoutError as exc:
        raise ValueError(
            f"Sandbox request timed out after {timeout_seconds:.2f}s"
        ) from exc

    if status != 200:
        raise ValueError(f"Snekbox request failed with HTTP {status}")

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Snekbox returned invalid JSON") from exc

    if not isinstance(decoded, dict):
        raise ValueError("Snekbox returned invalid payload")

    stdout = decoded.get("stdout")
    returncode = decoded.get("returncode")
    if not isinstance(stdout, str):
        raise ValueError("Snekbox payload missing stdout")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise ValueError("Snekbox payload missing return code")

    return SnekboxExecutionResult(stdout=stdout, returncode=returncode)
