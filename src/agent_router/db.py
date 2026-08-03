from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Required, TypedDict, Unpack

import aiosqlite
import structlog

logger = structlog.get_logger(__name__)

MAX_PERSISTED_BODY_BYTES = 256 * 1024

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
    input_price_per_million        REAL,
    output_price_per_million       REAL,
    cache_read_price_per_million   REAL,
    cache_write_price_per_million  REAL,
    cost_usd        REAL,
    failover_details TEXT
);

CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_calls_model ON calls(virtual_model);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
CREATE INDEX IF NOT EXISTS idx_calls_provider ON calls(provider_name, provider_model);
"""

CALL_SCHEMA_COLUMNS = frozenset(
    {
        "id",
        "timestamp",
        "virtual_model",
        "provider_name",
        "provider_type",
        "provider_model",
        "provider_url",
        "attempt",
        "latency_ms",
        "request_body",
        "request_tokens",
        "status",
        "error_type",
        "error_message",
        "response_body",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "input_price_per_million",
        "output_price_per_million",
        "cache_read_price_per_million",
        "cache_write_price_per_million",
        "cost_usd",
        "failover_details",
    }
)

CALL_SUMMARY_COLUMNS = (
    "id",
    "timestamp",
    "virtual_model",
    "provider_name",
    "provider_model",
    "attempt",
    "latency_ms",
    "status",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
)
_CALL_SUMMARY_SELECT = ", ".join(CALL_SUMMARY_COLUMNS)


class CallRecordPayload(TypedDict, total=False):
    """Keyword fields required to persist one completed API call."""

    virtual_model: Required[str]
    status: Required[str]
    provider_name: str | None
    provider_type: str | None
    provider_model: str | None
    provider_url: str | None
    attempt: int
    latency_ms: int | None
    request_body: dict | str | None
    request_tokens: int | None
    error_type: str | None
    error_message: str | None
    response_body: dict | str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    input_price_per_million: float | None
    output_price_per_million: float | None
    cache_read_price_per_million: float | None
    cache_write_price_per_million: float | None
    cost_usd: float | None
    failover_details: list[dict] | None


class IncompatibleDatabaseError(RuntimeError):
    """Indicate that an existing calls database needs manual replacement."""


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
        """Open the database after validating any existing calls schema.

        Existing databases are inspected through a read-only connection first. A
        schema mismatch is never migrated or overwritten automatically.

        Raises:
            IncompatibleDatabaseError: If the existing ``calls`` table is missing
                fields required by this version.
        """
        if self._conn is not None:
            return

        if self.db_path != Path(":memory:") and self.db_path.exists():
            await self._validate_existing_schema()

        conn = await aiosqlite.connect(str(self.db_path))
        try:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            await conn.commit()
        except Exception:
            await conn.close()
            raise

        self._conn = conn
        logger.info("db.init", path=str(self.db_path))

    async def _validate_existing_schema(self) -> None:
        """Reject an incompatible database without opening it for writes."""
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        conn = await aiosqlite.connect(uri, uri=True)
        try:
            table = await conn.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("calls",),
            )
            if not table:
                return
            rows = await conn.execute_fetchall("PRAGMA table_info(calls)")
        finally:
            await conn.close()

        existing_columns = {str(row[1]) for row in rows}
        missing_columns = sorted(CALL_SCHEMA_COLUMNS - existing_columns)
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise IncompatibleDatabaseError(
                "调用记录数据库 schema 与当前版本不兼容，"
                f"缺少字段: {missing}。请停止服务，备份后手动删除或重命名 "
                f"'{self.db_path}'，再重新启动以创建新数据库；"
                "程序未修改现有数据库。"
            )

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def record(self, **record: Unpack[CallRecordPayload]) -> str:
        """Persist one call and return its generated identifier.

        Price fields are snapshots of the final successful provider model.
        Callers omit them or pass ``None`` when no model completed successfully.
        """
        call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        request_body = record.get("request_body")
        response_body = record.get("response_body")
        failover_details = record.get("failover_details")
        request_tokens = record.get("request_tokens")
        if request_tokens is None and isinstance(request_body, dict):
            request_tokens = _estimate_request_tokens(request_body)
        resp_json = _serialize_call_body(response_body)
        req_json = _serialize_call_body(request_body)
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
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                input_price_per_million, output_price_per_million,
                cache_read_price_per_million, cache_write_price_per_million, cost_usd,
                failover_details
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )""",
            (
                call_id,
                now,
                record["virtual_model"],
                record.get("provider_name"),
                record.get("provider_type"),
                record.get("provider_model"),
                record.get("provider_url"),
                record.get("attempt", 1),
                record.get("latency_ms"),
                req_json,
                request_tokens,
                record["status"],
                record.get("error_type"),
                record.get("error_message"),
                resp_json,
                record.get("input_tokens"),
                record.get("output_tokens"),
                record.get("cache_read_tokens"),
                record.get("cache_write_tokens"),
                record.get("input_price_per_million"),
                record.get("output_price_per_million"),
                record.get("cache_read_price_per_million"),
                record.get("cache_write_price_per_million"),
                record.get("cost_usd"),
                fo_json,
            ),
        )
        await conn.commit()
        return call_id

    async def get_call(self, call_id: str) -> dict | None:
        """Return the complete persisted detail for one call."""
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
        provider: str | None = None,
        provider_model: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return lightweight call summaries and the matching total count.

        Request and response bodies, failover details, provider URLs, and price
        snapshots remain available only through :meth:`get_call`.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if model:
            conditions.append("virtual_model = ?")
            params.append(model)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if provider:
            conditions.append("provider_name = ?")
            params.append(provider)
        if provider_model:
            conditions.append("provider_model = ?")
            params.append(provider_model)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        conn = self.conn
        count_row = list(
            await conn.execute_fetchall(f"SELECT COUNT(*) FROM calls {where}", params)
        )
        total = count_row[0][0]

        offset = (page - 1) * size
        rows = await conn.execute_fetchall(
            f"SELECT {_CALL_SUMMARY_SELECT} FROM calls {where} "
            "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
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
                provider_name AS provider,
                provider_model AS model,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(input_tokens) AS total_input_tokens,
                SUM(output_tokens) AS total_output_tokens,
                SUM(cost_usd) AS total_cost_usd
            FROM calls
            WHERE provider_name IS NOT NULL AND provider_model IS NOT NULL
            GROUP BY provider_name, provider_model
            ORDER BY count DESC, provider_name, provider_model"""
        )
        return [dict(r) for r in rows]

    async def daily_trend(self, days: int = 30) -> list[dict]:
        """Return metrics for today and the preceding UTC calendar days.

        Args:
            days: Inclusive number of calendar days ending today.

        Returns:
            Existing daily aggregates in ascending date order. Days without
            calls are omitted for the Dashboard to fill explicitly.

        Raises:
            ValueError: If ``days`` is less than one.
        """
        if days < 1:
            raise ValueError("days 必须大于等于 1")
        rows = await self.conn.execute_fetchall(
            """SELECT
                DATE(timestamp) AS day,
                COUNT(*) AS count,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(input_tokens) AS input_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(cache_read_tokens) AS cache_read_tokens,
                SUM(cache_write_tokens) AS cache_write_tokens,
                SUM(cost_usd) AS cost_usd
            FROM calls
            WHERE timestamp >= DATE('now', ?)
            GROUP BY day ORDER BY day""",
            (f"-{days - 1} days",),
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


def _serialize_call_body(body: dict | str | None) -> str | None:
    """Serialize a call body to a bounded, valid JSON representation.

    Bodies larger than :data:`MAX_PERSISTED_BODY_BYTES` are replaced by a JSON
    envelope containing their original UTF-8 size and a textual prefix. Prefix
    length is selected against the final encoded envelope, accounting for JSON
    escaping and multi-byte characters without relying on an expansion ratio.
    """
    if not body:
        return None
    if isinstance(body, str):
        try:
            json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            serialized = json.dumps(body, ensure_ascii=False)
        else:
            serialized = body
    else:
        serialized = json.dumps(body, ensure_ascii=False)
    encoded = serialized.encode("utf-8")
    if len(encoded) <= MAX_PERSISTED_BODY_BYTES:
        return serialized

    envelope: dict[str, Any] = {
        "_truncated": True,
        "_original_bytes": len(encoded),
        "_preview": "",
    }
    best = json.dumps(envelope, ensure_ascii=False)
    low = 0
    # No prefix longer than the byte limit can fit, while bounding this search
    # also avoids repeatedly copying a complete 50 MiB source string.
    high = min(len(serialized), MAX_PERSISTED_BODY_BYTES)
    while low <= high:
        midpoint = (low + high) // 2
        envelope["_preview"] = serialized[:midpoint]
        candidate = json.dumps(envelope, ensure_ascii=False)
        if len(candidate.encode("utf-8")) <= MAX_PERSISTED_BODY_BYTES:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best
