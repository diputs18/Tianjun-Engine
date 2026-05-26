from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SQLiteStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def load_state(self) -> dict[str, Any]:
        with self.lock:
            nodes = [
                {
                    "payload": json.loads(row["payload_json"]),
                    "last_heartbeat_at": row["last_heartbeat_at"],
                }
                for row in self.conn.execute(
                    "SELECT payload_json, last_heartbeat_at FROM nodes ORDER BY node_id"
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
                    "SELECT payload_json FROM execution_records ORDER BY id"
                ).fetchall()
            ]
            decisions = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM decisions ORDER BY id"
                ).fetchall()
            ]
            policy_adjustments = [
                json.loads(row["payload_json"])
                for row in self.conn.execute(
                    "SELECT payload_json FROM policy_adjustments ORDER BY id"
                ).fetchall()
            ]
            control_state = {
                row["key"]: json.loads(row["value_json"])
                for row in self.conn.execute(
                    "SELECT key, value_json FROM control_state"
                ).fetchall()
            }
            return {
                "nodes": nodes,
                "tasks": tasks,
                "leases": leases,
                "execution_records": execution_records,
                "decisions": decisions,
                "policy_adjustments": policy_adjustments,
                "control_state": control_state,
            }

    def save_node(self, node_payload: dict[str, Any], last_heartbeat_at: float) -> None:
        payload_json = json.dumps(node_payload, ensure_ascii=True)
        now = time.time()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO nodes (node_id, payload_json, last_heartbeat_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    updated_at = excluded.updated_at
                """,
                (node_payload["node_id"], payload_json, last_heartbeat_at, now),
            )
            self.conn.commit()

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
            self.conn.commit()

    def delete_task(self, task_id: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            self.conn.commit()

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
            self.conn.commit()

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
            self.conn.commit()

    def delete_lease(self, task_id: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM leases WHERE task_id = ?", (task_id,))
            self.conn.commit()

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
            self.conn.commit()

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
            self.conn.commit()

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
            self.conn.commit()

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
            self.conn.commit()

    def _initialize_schema(self) -> None:
        with self.lock:
            self.conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                CREATE TABLE IF NOT EXISTS control_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    last_heartbeat_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS leases (
                    task_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS policy_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            self.conn.commit()
