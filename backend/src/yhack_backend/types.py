from typing import Literal, TypeAlias

Mode = Literal["zen", "casual", "ranked"]
Difficulty = Literal["easy", "medium", "hard", "expert"]
JsonScalar: TypeAlias = str | int | float | bool
