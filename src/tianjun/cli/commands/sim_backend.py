from __future__ import annotations

import json
from argparse import Namespace

from tianjun.config import TianjunConfig, first_present
from tianjun.simulation import run_simulation_backend


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    server = first_present(args.server, app_config.get("simulation.server"), app_config.get("agent.server"))
    max_cycles_value = first_present(args.max_cycles, app_config.get("simulation.max_cycles"))
    max_cycles = None if max_cycles_value is None else int(max_cycles_value)
    poll_interval = float(first_present(args.poll_interval, app_config.get("simulation.poll_interval_seconds"), default=1.0))
    time_scale = float(first_present(args.time_scale, app_config.get("simulation.time_scale"), default=0.08))
    if not server:
        raise ValueError("sim-backend requires --server or simulation.server/agent.server in config.")
    if args.verbose:
        print("Simulation backend running. Press Ctrl+C to stop.", flush=True)
    payload = run_simulation_backend(
        config_path=args.inventory,
        server=str(server),
        node_ids=args.node_id,
        max_cycles=max_cycles,
        poll_interval_seconds=poll_interval,
        time_scale=time_scale,
        verbose=bool(args.verbose),
    )
    if max_cycles is not None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
