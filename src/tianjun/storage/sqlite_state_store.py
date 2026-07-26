from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import sqlite_schema


class SQLiteStateStore:
    SCHEMA_VERSION = sqlite_schema.SCHEMA_VERSION
    MAX_HEARTBEATS = 10_000
    MAX_EXECUTION_RECORDS = 2_000
    MAX_DECISIONS = 2_000
    MAX_POLICY_ADJUSTMENTS = 1_000

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._heartbeat_writes = 0
        self._transaction_depth = 0
        try:
            self.last_migration_backup = sqlite_schema.initialize_schema(self.conn, self.path)
            self.integrity_status = sqlite_schema.quick_check(self.conn)
            self._prune_retained_history()
        except Exception:
            self.conn.close()
            raise

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    @property
    def schema_version(self) -> int:
        with self.lock:
            row = self.conn.execute("PRAGMA user_version").fetchone()
            return int(row[0])

    @contextmanager
    def transaction(self):
        """Group state writes into one atomic SQLite transaction."""
        with self.lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self.conn.execute("BEGIN IMMEDIATE")
            self._transaction_depth += 1
            try:
                yield self
            except Exception:
                self._transaction_depth -= 1
                if outermost:
                    self.conn.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self.conn.commit()

    def _commit_locked(self) -> None:
        if self._transaction_depth == 0:
            self.conn.commit()

    def readiness(self) -> dict[str, Any]:
        """Verify that the state database accepts a reversible write."""
        with self.lock:
            try:
                integrity = sqlite_schema.quick_check(self.conn)
                if integrity != "ok":
                    return {"ready": False, "integrity": integrity, "writable": False}
                self.conn.execute("SAVEPOINT tianjun_readiness")
                self.conn.execute(
                    """
                    INSERT INTO control_state (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    ("__readiness_probe__", "true", time.time()),
                )
                self.conn.execute("ROLLBACK TO tianjun_readiness")
                self.conn.execute("RELEASE tianjun_readiness")
                return {"ready": True, "integrity": "ok", "writable": True}
            except sqlite3.Error as exc:
                try:
                    self.conn.execute("ROLLBACK TO tianjun_readiness")
                    self.conn.execute("RELEASE tianjun_readiness")
                except sqlite3.Error:
                    pass
                return {
                    "ready": False,
                    "integrity": "error",
                    "writable": False,
                    "error": type(exc).__name__,
                }

    def load_state(self) -> dict[str, Any]:
        with self.lock:
            nodes = [
                {
                    "payload": json.loads(row["payload_json"]),
                    "last_seen_epoch": row["last_seen_epoch"],
                }
                for row in self.conn.execute(
                    "SELECT payload_json, last_seen_epoch FROM nodes ORDER BY node_id"
                ).fetchall()
            ]
            tasks = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM tasks ORDER BY task_id"
                ).fetchall()
            ]
            leases = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM leases ORDER BY task_id"
                ).fetchall()
            ]
            execution_records = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM (SELECT id, payload_json FROM execution_records ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (self.MAX_EXECUTION_RECORDS,),
                ).fetchall()
            ]
            decisions = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM (SELECT id, payload_json FROM decisions ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (self.MAX_DECISIONS,),
                ).fetchall()
            ]
            policy_adjustments = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM (SELECT id, payload_json FROM policy_adjustments ORDER BY id DESC LIMIT ?) ORDER BY id",
                    (self.MAX_POLICY_ADJUSTMENTS,),
                ).fetchall()
            ]
            control_state = {
                row["key"]: json.loads(row["value_json"])
                for row in self.conn.execute(
                    "SELECT key, value_json FROM control_state"
                ).fetchall()
            }
            task_batches = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM task_batches ORDER BY created_at, batch_id"
                ).fetchall()
            ]
            batch_plans = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM batch_plans ORDER BY created_at, plan_id"
                ).fetchall()
            ]
            reservation_ledgers = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM reservation_ledgers ORDER BY plan_id"
                ).fetchall()
            ]
            return {
                "nodes": nodes,
                "tasks": tasks,
                "leases": leases,
                "execution_records": execution_records,
                "decisions": decisions,
                "policy_adjustments": policy_adjustments,
                "control_state": control_state,
                "task_batches": task_batches,
                "batch_plans": batch_plans,
                "reservation_ledgers": reservation_ledgers,
            }

    def save_node(self, node_payload: dict[str, Any], last_seen_epoch: float) -> None:
        payload_json = json.dumps(node_payload, ensure_ascii=True)
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO nodes (node_id, payload_json, last_heartbeat_at, last_seen_epoch, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    last_seen_epoch = excluded.last_seen_epoch,
                    updated_at = excluded.updated_at
                """,
                (node_payload["node_id"], payload_json, last_seen_epoch, last_seen_epoch, now),
            )
            self._commit_locked()

    def save_task(self, task_payload: dict[str, Any]) -> None:
        payload_json = json.dumps(task_payload, ensure_ascii=True)
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO tasks (task_id, status, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (task_payload["task_id"], task_payload["status"], payload_json, now),
            )
            self._commit_locked()

    def delete_task(self, task_id: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            self._commit_locked()

    def record_heartbeat(self, node_id: str, payload: dict[str, Any]) -> None:
        now = time.time()
        payload_json = json.dumps(payload, ensure_ascii=True)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO heartbeats (node_id, payload_json, created_at)
                VALUES (?, ?, ?)
                """,
                (node_id, payload_json, now),
            )
            self._heartbeat_writes += 1
            if self._heartbeat_writes % 256 == 0:
                self._prune_table_locked("heartbeats", self.MAX_HEARTBEATS)
            self._commit_locked()

    def save_lease(self, lease_payload: dict[str, Any]) -> None:
        payload_json = json.dumps(lease_payload, ensure_ascii=True)
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO leases (task_id, node_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    node_id = excluded.node_id,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (lease_payload["task_id"], lease_payload["node_id"], payload_json, now),
            )
            self._commit_locked()

    def delete_lease(self, task_id: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM leases WHERE task_id = ?", (task_id,))
            self._commit_locked()

    def append_execution_record(self, record_payload: dict[str, Any]) -> None:
        now = time.time()
        payload_json = json.dumps(record_payload, ensure_ascii=True)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO execution_records (task_id, node_id, success, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record_payload["task_id"],
                    record_payload["node_id"],
                    1 if record_payload["success"] else 0,
                    payload_json,
                    now,
                ),
            )
            self._prune_table_locked("execution_records", self.MAX_EXECUTION_RECORDS)
            self._commit_locked()

    def append_decision(self, decision_payload: dict[str, Any]) -> None:
        now = time.time()
        payload_json = json.dumps(decision_payload, ensure_ascii=True)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO decisions (task_id, node_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (decision_payload["task_id"], decision_payload["node_id"], payload_json, now),
            )
            self._prune_table_locked("decisions", self.MAX_DECISIONS)
            self._commit_locked()

    def append_policy_adjustment(self, adjustment_payload: dict[str, Any]) -> None:
        now = time.time()
        payload_json = json.dumps(adjustment_payload, ensure_ascii=True)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO policy_adjustments (tick, payload_json, created_at)
                VALUES (?, ?, ?)
                """,
                (adjustment_payload["tick"], payload_json, now),
            )
            self._prune_table_locked("policy_adjustments", self.MAX_POLICY_ADJUSTMENTS)
            self._commit_locked()

    def set_control_value(self, key: str, value: Any) -> None:
        now = time.time()
        value_json = json.dumps(value, ensure_ascii=True)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO control_state (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, value_json, now),
            )
            self._commit_locked()

    def save_task_batch(self, batch_payload: dict[str, Any]) -> None:
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO task_batches (batch_id, client_batch_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    client_batch_id = excluded.client_batch_id,
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    batch_payload["batch_id"],
                    batch_payload["client_batch_id"],
                    batch_payload["status"],
                    json.dumps(batch_payload, ensure_ascii=True),
                    now,
                    now,
                ),
            )
            self._commit_locked()

    def save_batch_plan(self, plan_payload: dict[str, Any]) -> None:
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO batch_plans (plan_id, batch_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    plan_payload["plan_id"],
                    plan_payload["batch_id"],
                    plan_payload["status"],
                    json.dumps(plan_payload, ensure_ascii=True),
                    now,
                    now,
                ),
            )
            self._commit_locked()

    def save_reservation_ledger(self, ledger_payload: dict[str, Any]) -> None:
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO reservation_ledgers (plan_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    ledger_payload["plan_id"],
                    json.dumps(ledger_payload, ensure_ascii=True),
                    now,
                ),
            )
            self._commit_locked()

    def _prune_retained_history(self) -> None:
        with self.lock:
            self._prune_table_locked("heartbeats", self.MAX_HEARTBEATS)
            self._prune_table_locked("execution_records", self.MAX_EXECUTION_RECORDS)
            self._prune_table_locked("decisions", self.MAX_DECISIONS)
            self._prune_table_locked("policy_adjustments", self.MAX_POLICY_ADJUSTMENTS)
            self.conn.commit()

    def _prune_table_locked(self, table: str, keep: int) -> None:
        allowed = {"heartbeats", "execution_records", "decisions", "policy_adjustments"}
        if table not in allowed:
            raise ValueError(f"unsupported retention table: {table}")
        self.conn.execute(
            f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY id DESC LIMIT ?)",
            (max(1, int(keep)),),
        )
