from __future__ import annotations

from typing import Literal, TypeAlias

Mode = Literal["zen", "casual", "ranked"]
Difficulty = Literal["easy", "medium", "hard", "expert"]
JsonScalar: TypeAlias = str | int | float | bool
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
