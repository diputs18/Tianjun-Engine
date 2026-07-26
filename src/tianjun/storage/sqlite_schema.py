from __future__ import annotations

import sqlite3
import time
from pathlib import Path


SCHEMA_VERSION = 2

BASE_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS control_state (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        node_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        last_heartbeat_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leases (
        task_id TEXT PRIMARY KEY,
        node_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS heartbeats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        node_id TEXT NOT NULL,
        success INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tick INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )
    """,
)

V2_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS task_batches (
        batch_id TEXT PRIMARY KEY,
        client_batch_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS batch_plans (
        plan_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_batch_plans_batch_id ON batch_plans(batch_id)",
    """
    CREATE TABLE IF NOT EXISTS reservation_ledgers (
        plan_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
)

REQUIRED_TABLES = {
    "control_state",
    "nodes",
    "tasks",
    "leases",
    "heartbeats",
    "decisions",
    "execution_records",
    "policy_adjustments",
    "task_batches",
    "batch_plans",
    "reservation_ledgers",
}


class UnsupportedSchemaVersion(RuntimeError):
    pass


def quick_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA quick_check").fetchone()
    return "unknown" if row is None else str(row[0])


def initialize_schema(connection: sqlite3.Connection, path: Path) -> Path | None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"Database schema v{current_version} is newer than supported v{SCHEMA_VERSION}."
        )
    integrity = quick_check(connection)
    if integrity != "ok":
        raise sqlite3.DatabaseError(f"SQLite quick_check failed: {integrity}")

    backup_path = None
    if current_version < SCHEMA_VERSION and _has_user_tables(connection):
        backup_path = _backup_before_migration(connection, path, current_version)

    if current_version < SCHEMA_VERSION:
        try:
            connection.execute("BEGIN IMMEDIATE")
            _create_base_schema(connection)
            _migrate_to_v2(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            _validate_schema(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    else:
        _validate_schema(connection)

    integrity = quick_check(connection)
    if integrity != "ok":
        raise sqlite3.DatabaseError(f"SQLite quick_check failed after migration: {integrity}")
    return backup_path


def _create_base_schema(connection: sqlite3.Connection) -> None:
    for statement in BASE_SCHEMA_STATEMENTS:
        connection.execute(statement)


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(nodes)").fetchall()
    }
    if "last_seen_epoch" not in columns:
        connection.execute("ALTER TABLE nodes ADD COLUMN last_seen_epoch REAL")
    connection.execute(
        "UPDATE nodes SET last_seen_epoch = updated_at WHERE last_seen_epoch IS NULL"
    )
    for statement in V2_SCHEMA_STATEMENTS:
        connection.execute(statement)


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise sqlite3.DatabaseError(f"SQLite schema is missing tables: {', '.join(missing)}")
    node_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(nodes)").fetchall()
    }
    if "last_seen_epoch" not in node_columns:
        raise sqlite3.DatabaseError("SQLite nodes table is missing last_seen_epoch")


def _has_user_tables(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    return row is not None


def _backup_before_migration(
    connection: sqlite3.Connection,
    path: Path,
    current_version: int,
) -> Path | None:
    if str(path) == ":memory:":
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(
        f"{path.name}.pre-v{SCHEMA_VERSION}-from-v{current_version}-{stamp}-{time.time_ns() % 1_000_000:06d}.bak"
    )
    backup_connection = sqlite3.connect(str(backup_path))
    try:
        connection.backup(backup_connection)
        if quick_check(backup_connection) != "ok":
            raise sqlite3.DatabaseError("SQLite migration backup failed integrity check")
    except Exception:
        backup_connection.close()
        backup_path.unlink(missing_ok=True)
        raise
    else:
        backup_connection.close()
    return backup_path
