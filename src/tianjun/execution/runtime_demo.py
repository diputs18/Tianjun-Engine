from __future__ import annotations

from pathlib import Path
from typing import Any

from ..application.bootstrap import build_control_plane
from ..node_agent.clients import DirectControlPlaneClient
from ..node_agent.runtime import LightweightNodeAgent
from ..scenarios import load_scenario_payload, node_from_dict, task_from_dict
from ..storage.sqlite_state_store import SQLiteStateStore


def run_runtime_demo(
    scenario_path: str | Path,
    *,
    max_rounds: int = 40,
    poll_interval_seconds: float = 0.0,
    state_db_path: str | Path | None = None,
    model_dir: str | Path | None = None,
    require_model: bool = False,
) -> dict[str, Any]:
    state_store = None if state_db_path is None else SQLiteStateStore(state_db_path)
    try:
        payload = load_scenario_payload(scenario_path)
        control_plane = build_control_plane(
            state_store=state_store,
            model_dir=model_dir,
            require_model=require_model,
        )
        client = DirectControlPlaneClient(control_plane)

        agents = []
        for node_data in payload.get("nodes", []):
            agent = LightweightNodeAgent(
                node=node_from_dict(node_data),
                control_plane_client=client,
                poll_interval_seconds=poll_interval_seconds,
            )
            agent.register()
            agents.append(agent)

        for task_data in payload.get("tasks", []):
            task = task_from_dict(task_data)
            if task.task_id not in control_plane.tasks:
                client.submit_task(task)

        history: list[dict[str, Any]] = []
        idle_rounds = 0
        for _ in range(max_rounds):
            progressed = False
            for agent in agents:
                outcome = agent.run_once()
                if outcome is not None:
                    progressed = True
                    history.append(outcome)

            report = client.get_report()
            if not progressed and report["totals"]["pending_tasks"] == 0 and report["totals"]["leased_tasks"] == 0:
                idle_rounds += 1
                if idle_rounds >= 2:
                    break
            else:
                idle_rounds = 0

        return {
            "history": history,
            "report": client.get_report(),
        }
    finally:
        if state_store is not None:
            state_store.close()
