from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _use_local_snekbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YHACK_SNEKBOX_URL", "local://")
