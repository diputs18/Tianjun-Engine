from __future__ import annotations

import sqlite3
import time

import pytest

from tianjun.application.control_plane import CentralControlPlane
from tianjun.domain import Node, ResourceVector
from tianjun.storage.sqlite_state_store import SQLiteStateStore
from tianjun.storage.sqlite_schema import UnsupportedSchemaVersion
from tianjun.storage import sqlite_schema


def _batch_payload(client_batch_id: str = "persisted-client") -> dict:
    return {
        "client_batch_id": client_batch_id,
        "batch_name": "持久化回归",
        "tasks": [
            {
                "task_id": "persisted-task",
                "task_type": "batch",
                "demand": {"cpu": 1, "memory": 1, "storage": 1},
                "estimated_duration": 3,
                "priority": 5,
            }
        ],
    }


def _control_with_node(store: SQLiteStateStore) -> CentralControlPlane:
    control = CentralControlPlane(state_store=store)
    if "node-a" not in control.nodes:
        control.register_node(Node(
            node_id="node-a",
            region="dc1",
            capacity=ResourceVector(cpu=4, memory=8, storage=20),
        ))
    return control


def test_sqlite_v1_migrates_monotonic_heartbeat_to_wall_clock_epoch(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    updated_at = time.time() - 3.0
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE nodes (node_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, last_heartbeat_at REAL NOT NULL, updated_at REAL NOT NULL)"
    )
    connection.execute(
        "INSERT INTO nodes VALUES (?, ?, ?, ?)",
        ("node-a", '{"node_id":"node-a"}', 12.5, updated_at),
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    store = SQLiteStateStore(path)
    try:
        assert store.schema_version == 2
        assert store.load_state()["nodes"][0]["last_seen_epoch"] == pytest.approx(updated_at)
        assert store.last_migration_backup is not None
        assert store.last_migration_backup.is_file()
        backup = sqlite3.connect(store.last_migration_backup)
        try:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        finally:
            backup.close()
    finally:
        store.close()


def test_sqlite_rejects_future_schema_without_downgrading(tmp_path) -> None:
    path = tmp_path / "future.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()

    with pytest.raises(UnsupportedSchemaVersion, match="newer than supported"):
        SQLiteStateStore(path)

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 99
    finally:
        check.close()


def test_failed_schema_migration_is_atomic(tmp_path, monkeypatch) -> None:
    path = tmp_path / "failed-migration.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE nodes (node_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, last_heartbeat_at REAL NOT NULL, updated_at REAL NOT NULL)"
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    def fail_after_schema_change(connection):
        connection.execute("ALTER TABLE nodes ADD COLUMN last_seen_epoch REAL")
        connection.execute("CREATE TABLE should_rollback (value TEXT)")
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(sqlite_schema, "_migrate_to_v2", fail_after_schema_change)
    with pytest.raises(RuntimeError, match="migration failure"):
        SQLiteStateStore(path)

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {
            row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        columns = {row[1] for row in check.execute("PRAGMA table_info(nodes)")}
        assert "should_rollback" not in tables
        assert "last_seen_epoch" not in columns
    finally:
        check.close()


def test_sqlite_readiness_performs_reversible_write(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "ready.db")
    try:
        assert store.readiness() == {"ready": True, "integrity": "ok", "writable": True}
        assert "__readiness_probe__" not in store.load_state()["control_state"]
    finally:
        store.close()


def test_sqlite_transaction_rolls_back_all_grouped_writes(tmp_path) -> None:
    store = SQLiteStateStore(tmp_path / "transaction.db")
    try:
        with pytest.raises(RuntimeError):
            with store.transaction():
                store.set_control_value("partial", {"written": True})
                store.save_task({"task_id": "partial-task", "status": "pending"})
                raise RuntimeError("abort")

        snapshot = store.load_state()
        assert "partial" not in snapshot["control_state"]
        assert snapshot["tasks"] == []
    finally:
        store.close()


def test_batch_plan_idempotency_and_reservations_survive_restart(tmp_path) -> None:
    path = tmp_path / "batch.db"
    store = SQLiteStateStore(path)
    control = _control_with_node(store)
    imported = control.import_task_batch(_batch_payload())
    plan = control.preview_batch_schedule(imported["batch_id"], {"strategy": "B1-batch-greedy"})
    store.close()

    restored_store = SQLiteStateStore(path)
    restored = CentralControlPlane(state_store=restored_store)
    replay = restored.import_task_batch(_batch_payload())
    assert replay["idempotent_replay"] is True
    assert replay["batch_id"] == imported["batch_id"]
    assert restored.get_task_batch(imported["batch_id"])["latest_plan"]["plan_id"] == plan["plan_id"]

    committed = restored.commit_batch_schedule(imported["batch_id"], {
        "plan_id": plan["plan_id"],
        "resource_snapshot_version": plan["resource_snapshot_version"],
        "confirmed_by_user_button": True,
    })
    assert committed["reservation_ledger"]["reservations"]
    restored_store.close()

    final_store = SQLiteStateStore(path)
    try:
        final = CentralControlPlane(state_store=final_store)
        assert final.batch_plans[plan["plan_id"]].status == "committed"
        assert plan["plan_id"] in final.reservation_ledgers
        assert "persisted-task" in final.pending_queue
    finally:
        final_store.close()


def test_wall_clock_heartbeat_expires_after_restart(tmp_path) -> None:
    path = tmp_path / "heartbeat.db"
    store = SQLiteStateStore(path)
    control = CentralControlPlane(state_store=store, heartbeat_timeout_seconds=1.0)
    control.register_node(Node(node_id="cloudsim-node", region="dc1", labels={"cloudsim"}, capacity=ResourceVector(cpu=2)))
    control.last_heartbeat_epoch["cloudsim-node"] = time.time() - 10.0
    control._persist_node(control.nodes["cloudsim-node"])
    store.close()

    restored_store = SQLiteStateStore(path)
    try:
        restored = CentralControlPlane(state_store=restored_store, heartbeat_timeout_seconds=1.0)
        assert restored.build_report()["nodes"][0]["online"] is False
    finally:
        restored_store.close()


def test_failed_batch_persistence_rolls_back_memory_and_database(tmp_path, monkeypatch) -> None:
    path = tmp_path / "rollback.db"
    store = SQLiteStateStore(path)
    control = _control_with_node(store)
    imported = control.import_task_batch(_batch_payload("rollback-client"))
    plan = control.preview_batch_schedule(imported["batch_id"], {"strategy": "B1-batch-greedy"})

    def fail_ledger(_payload):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(store, "save_reservation_ledger", fail_ledger)
    with pytest.raises(RuntimeError, match="storage failure"):
        control.commit_batch_schedule(imported["batch_id"], {
            "plan_id": plan["plan_id"],
            "resource_snapshot_version": plan["resource_snapshot_version"],
            "confirmed_by_user_button": True,
        })

    assert control.leases == {}
    assert control.reservation_ledgers == {}
    assert "persisted-task" not in control.tasks
    assert control.nodes["node-a"].used().cpu == 0
    store.close()

    reopened = SQLiteStateStore(path)
    try:
        persisted = reopened.load_state()
        stored_plan = next(item for item in persisted["batch_plans"] if item["plan_id"] == plan["plan_id"])
        assert stored_plan["status"] == "previewed"
        assert persisted["reservation_ledgers"] == []
    finally:
        reopened.close()
