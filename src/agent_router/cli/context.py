from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class CliContext:
    config: str
    db: str
    output: Literal["json", "table"]
    host: str | None = None
    port: int | None = None
