from __future__ import annotations

import sqlite3

import pytest

from agent_router.db import (
    CALL_SCHEMA_COLUMNS,
    SCHEMA,
    CallStore,
    IncompatibleDatabaseError,
)

PRICE_SNAPSHOT_COLUMNS = (
    "input_price_per_million",
    "output_price_per_million",
    "cache_read_price_per_million",
    "cache_write_price_per_million",
)


async def test_fresh_database_has_complete_calls_schema(tmp_path):
    db_path = tmp_path / "calls.db"
    store = CallStore(str(db_path))

    await store.init()
    try:
        rows = await store.conn.execute_fetchall("PRAGMA table_info(calls)")
    finally:
        await store.close()

    assert {str(row[1]) for row in rows} == CALL_SCHEMA_COLUMNS


async def test_record_preserves_null_and_zero_price_snapshots(tmp_path):
    store = CallStore(str(tmp_path / "calls.db"))
    await store.init()
    try:
        zero_id = await store.record(
            virtual_model="router",
            status="success",
            provider_name="provider",
            provider_model="model",
            input_price_per_million=0.0,
            output_price_per_million=0.0,
            cache_read_price_per_million=0.0,
            cache_write_price_per_million=0.0,
            cost_usd=0.0,
        )
        null_id = await store.record(
            virtual_model="router",
            status="error",
            error_type="upstream_error",
        )

        zero_call = await store.get_call(zero_id)
        null_call = await store.get_call(null_id)
    finally:
        await store.close()

    assert zero_call is not None
    assert null_call is not None
    for column in PRICE_SNAPSHOT_COLUMNS:
        assert zero_call[column] == 0.0
        assert null_call[column] is None


async def test_incompatible_database_is_unchanged_after_validation_failure(tmp_path):
    db_path = tmp_path / "legacy-calls.db"
    legacy_schema = "\n".join(
        line
        for line in SCHEMA.splitlines()
        if not any(column in line for column in PRICE_SNAPSHOT_COLUMNS)
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(legacy_schema)
        conn.execute(
            """INSERT INTO calls (id, timestamp, virtual_model, status)
            VALUES (?, ?, ?, ?)""",
            ("legacy-id", "2026-07-13T00:00:00+00:00", "router", "success"),
        )
        conn.commit()
    finally:
        conn.close()

    original_bytes = db_path.read_bytes()
    store = CallStore(str(db_path))

    with pytest.raises(IncompatibleDatabaseError) as exc_info:
        await store.init()

    message = str(exc_info.value)
    assert "schema 与当前版本不兼容" in message
    assert "手动删除或重命名" in message
    for column in PRICE_SNAPSHOT_COLUMNS:
        assert column in message
    with pytest.raises(RuntimeError, match="未初始化"):
        _ = store.conn
    assert db_path.read_bytes() == original_bytes

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, virtual_model, status FROM calls WHERE id = ?",
            ("legacy-id",),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("legacy-id", "router", "success")
