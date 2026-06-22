from __future__ import annotations

import json
from typing import Any, Literal

from rich.console import Console
from rich.table import Table

console = Console()


def emit(data: Any, output_fmt: Literal["json", "table"]) -> None:
    """以 JSON 或 Rich 表格输出数据."""
    if output_fmt == "json":
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
        return

    if isinstance(data, dict):
        if data and all(isinstance(v, (str, int, float, bool, type(None))) for v in data.values()):
            table = Table(show_header=True, header_style="bold")
            table.add_column("Key")
            table.add_column("Value")
            for k, v in data.items():
                table.add_row(str(k), str(v))
            console.print(table)
            return
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
        return

    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys: list[str] = []
        for row in data:
            for k in row:
                if k not in keys:
                    keys.append(k)
        table = Table(show_header=True, header_style="bold")
        for k in keys:
            table.add_column(k)
        for row in data:
            table.add_row(*(str(row.get(k, "")) for k in keys))
        console.print(table)
        return

    console.print(str(data))
