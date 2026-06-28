from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    virtual_model   TEXT NOT NULL,
    provider_name   TEXT,
    provider_type   TEXT,
    provider_model  TEXT,
    provider_url    TEXT,
    attempt         INTEGER DEFAULT 1,
    latency_ms      INTEGER,
    request_body    TEXT,
    request_tokens  INTEGER,
    status          TEXT NOT NULL,
    error_type      TEXT,
    error_message   TEXT,
    response_body   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cache_read_tokens   INTEGER,
    cache_write_tokens  INTEGER,
    cost_usd        REAL,
    failover_details TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_calls_model ON calls(virtual_model);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
"""


class CallStore:
    def __init__(self, db_path: str = "calls.db") -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("CallStore 未初始化，请先调用 init()")
        return self._conn

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        # Migration: add failover_details column if missing (pre-existing DBs)
        try:
            await self._conn.execute(
                "ALTER TABLE calls ADD COLUMN failover_details TEXT"
            )
        except aiosqlite.OperationalError:
            pass  # column already exists
        await self._conn.commit()
        logger.info("db.init", path=str(self.db_path))

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def record(
        self,
        *,
        virtual_model: str,
        status: str,
        provider_name: str | None = None,
        provider_type: str | None = None,
        provider_model: str | None = None,
        provider_url: str | None = None,
        attempt: int = 1,
        latency_ms: int | None = None,
        request_body: dict | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        response_body: dict | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        cost_usd: float | None = None,
        failover_details: list[dict] | None = None,
    ) -> str:
        call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        request_tokens = _estimate_request_tokens(request_body)
        resp_json = (
            json.dumps(response_body, ensure_ascii=False) if response_body else None
        )
        req_json = (
            json.dumps(request_body, ensure_ascii=False) if request_body else None
        )
        fo_json = (
            json.dumps(failover_details, ensure_ascii=False)
            if failover_details
            else None
        )

        conn = self.conn
        await conn.execute(
            """INSERT INTO calls (
                id, timestamp, virtual_model, provider_name, provider_type, provider_model,
                provider_url, attempt, latency_ms, request_body, request_tokens,
                status, error_type, error_message, response_body,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
                failover_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                call_id,
                now,
                virtual_model,
                provider_name,
                provider_type,
                provider_model,
                provider_url,
                attempt,
                latency_ms,
                req_json,
                request_tokens,
                status,
                error_type,
                error_message,
                resp_json,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
                cost_usd,
                fo_json,
            ),
        )
        await conn.commit()
        return call_id

    async def get_call(self, call_id: str) -> dict | None:
        async with self.conn.execute(
            "SELECT * FROM calls WHERE id = ?", (call_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_calls(
        self,
        page: int = 1,
        size: int = 50,
        model: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        conditions: list[str] = []
        params: list[Any] = []
        if model:
            conditions.append("virtual_model = ?")
            params.append(model)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        conn = self.conn
        count_row = list(
            await conn.execute_fetchall(f"SELECT COUNT(*) FROM calls {where}", params)
        )
        total = count_row[0][0]

        offset = (page - 1) * size
        rows = await conn.execute_fetchall(
            f"SELECT * FROM calls {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, size, offset],
        )
        return [dict(r) for r in rows], total

    async def summary(self) -> dict:
        """返回概览统计."""
        row = list(
            await self.conn.execute_fetchall(
                """SELECT
                COUNT(*) AS total_calls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cache_read_tokens) AS total_cache_read,
                SUM(cache_write_tokens) AS total_cache_write,
                SUM(cost_usd) AS total_cost_usd,
                AVG(CASE WHEN status = 'success' THEN latency_ms END) AS avg_latency_ms
            FROM calls"""
            )
        )
        r = dict(row[0])
        total = r["total_calls"] or 0
        success = r["success_count"] or 0
        return {
            "total_calls": total,
            "success_count": success,
            "error_count": total - success,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0,
            "total_input_tokens": r["total_input_tokens"] or 0,
            "total_output_tokens": r["total_output_tokens"] or 0,
            "total_cache_read": r["total_cache_read"] or 0,
            "total_cache_write": r["total_cache_write"] or 0,
            "total_cost_usd": round(r["total_cost_usd"] or 0, 6),
            "avg_latency_ms": round(r["avg_latency_ms"] or 0),
        }

    async def by_model(self) -> list[dict]:
        rows = await self.conn.execute_fetchall(
            """SELECT
                virtual_model,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cost_usd) AS total_cost_usd
            FROM calls GROUP BY virtual_model"""
        )
        return [dict(r) for r in rows]

    async def by_provider(self) -> list[dict]:
        rows = await self.conn.execute_fetchall(
            """SELECT
                COALESCE(provider_type, 'unknown') AS provider,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count
            FROM calls GROUP BY provider_type"""
        )
        return [dict(r) for r in rows]

    async def by_real_model(self) -> list[dict]:
        rows = await self.conn.execute_fetchall(
            """SELECT
                COALESCE(provider_model, 'unknown') AS model,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cost_usd) AS total_cost_usd
            FROM calls WHERE provider_model IS NOT NULL
            GROUP BY provider_model"""
        )
        return [dict(r) for r in rows]

    async def daily_trend(self, days: int = 30) -> list[dict]:
        rows = await self.conn.execute_fetchall(
            """SELECT
                DATE(timestamp) AS day,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(cost_usd) AS cost_usd
            FROM calls
            WHERE timestamp >= DATE('now', ?)
            GROUP BY day ORDER BY day""",
            (f"-{days} days",),
        )
        return [dict(r) for r in rows]


def _estimate_request_tokens(body: dict | None) -> int | None:
    """粗略估算请求 token 数 (用于流式请求无法从响应获取时)."""
    if not body:
        return None
    messages = body.get("messages", [])
    if not messages:
        return None
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total_chars += len(block.get("text", ""))
                elif isinstance(block, dict) and block.get("type") == "image":
                    # base64 图片数据 ≈ token 数的 1/3
                    source = block.get("source", {})
                    data = source.get("data", "")
                    total_chars += len(data) // 3
    system = body.get("system", "")
    if isinstance(system, str):
        total_chars += len(system)
    elif isinstance(system, list):
        for s in system:
            if isinstance(s, dict):
                total_chars += len(s.get("text", ""))
    # 粗略估算: 英文 ~4 chars/token, 中文 ~1.5 chars/token
    return max(1, int(total_chars / 3))
