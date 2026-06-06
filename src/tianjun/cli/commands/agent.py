from __future__ import annotations

import json
from argparse import Namespace

from tianjun.cli import resolved_path_setting
from tianjun.config import TianjunConfig, first_present
from tianjun.node_agent.clients import HttpControlPlaneClient
from tianjun.node_agent.runtime import LightweightNodeAgent
from tianjun.scenarios import load_scenario_payload, node_from_dict


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    server = first_present(args.server, app_config.get("agent.server"))
    scenario = resolved_path_setting(args.scenario, app_config, "agent.scenario", "scenario.path")
    node_id = first_present(args.node_id, app_config.get("agent.node_id"))
    max_cycles = int(first_present(args.max_cycles, app_config.get("agent.max_cycles"), default=30))
    poll_interval = float(first_present(args.poll_interval, app_config.get("agent.poll_interval_seconds"), default=1.0))
    if not server:
        raise ValueError("agent requires --server or agent.server in config.")
    if scenario is None:
        raise ValueError("agent requires --scenario or agent.scenario/scenario.path in config.")
    if not node_id:
        raise ValueError("agent requires --node-id or agent.node_id in config.")
    payload = load_scenario_payload(scenario)
    node_data = next((item for item in payload.get("nodes", []) if item["node_id"] == node_id), None)
    if node_data is None:
        raise ValueError(f"Node {node_id} was not found in {scenario}.")
    agent = LightweightNodeAgent(
        node=node_from_dict(node_data),
        control_plane_client=HttpControlPlaneClient(str(server)),
        poll_interval_seconds=poll_interval,
    )
    agent.register()
    results = agent.run_until_idle(max_cycles=max_cycles)
    print(json.dumps({"node_id": node_id, "completed": results}, indent=2, ensure_ascii=True))
