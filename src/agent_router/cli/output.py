from __future__ import annotations

from typing import Any, Literal

from rich.console import Console
from rich.table import Table

console = Console()


def _print_records_table(records: list[dict]) -> None:
    """将 dict 列表渲染为 Rich 表格（列按首次出现顺序聚合）。"""
    keys: list[str] = []
    for row in records:
        for k in row:
            if k not in keys:
                keys.append(k)
    table = Table(show_header=True, header_style="bold")
    for k in keys:
        table.add_column(k)
    for row in records:
        table.add_row(*(str(row.get(k, "")) for k in keys))
    console.print(table)


def emit(data: Any, output_fmt: Literal["json", "table"]) -> None:
    """以 JSON 或 Rich 表格输出数据."""
    if output_fmt == "json":
        # Rich 的 print_json 原生支持 data= 传对象与 default/ensure_ascii，无需先 json.dumps。
        # highlight=False 避免给键值加 ANSI 颜色码，保证 JSON 输出是机器可解析的纯文本。
        console.print_json(data=data, default=str, ensure_ascii=False, highlight=False)
        return

    # 分页/包装 envelope: {"data": [ {...}, ... ], ...其余标量键...}
    # 将 data 渲染为表格、其余键作为摘要输出，避免 --output table 被静默回退为 JSON。
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list) and inner and all(isinstance(r, dict) for r in inner):
            meta = {k: v for k, v in data.items() if k != "data"}
            if meta and all(
                isinstance(v, (str, int, float, bool, type(None))) for v in meta.values()
            ):
                console.print(
                    "  ".join(f"{k}={v}" for k, v in meta.items()),
                    style="dim",
                )
            _print_records_table(inner)
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
        console.print_json(data=data, default=str, ensure_ascii=False, highlight=False)
        return

    if isinstance(data, list) and data and isinstance(data[0], dict):
        _print_records_table(data)
        return

    console.print(str(data))
