from __future__ import annotations

ADMIN_USERNAME = "admin"


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def is_admin_username(value: str) -> bool:
    return normalize_username(value) == normalize_username(ADMIN_USERNAME)
