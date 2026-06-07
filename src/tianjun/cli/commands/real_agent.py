from __future__ import annotations

from argparse import Namespace

from tianjun.cli import resolved_path_setting
from tianjun.config import TianjunConfig, config_bool, first_present
from tianjun.node_agent.real_probe import run_real_node_agent


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    server = first_present(args.server, app_config.get("real_agent.server"))
    node_config = resolved_path_setting(args.node_config, app_config, "real_agent.node_config")
    once = bool(args.once or config_bool(app_config.get("real_agent.once"), default=False))
    execute = bool(args.execute or config_bool(app_config.get("real_agent.execute"), default=False))
    max_cycles = first_present(args.max_cycles, app_config.get("real_agent.max_cycles"))
    if max_cycles is not None:
        max_cycles = int(max_cycles)
    if not server:
        raise ValueError("real-agent requires --server or real_agent.server in config.")
    if node_config is None:
        raise ValueError("real-agent requires --node-config or real_agent.node_config in config.")
    run_real_node_agent(
        config_path=node_config,
        server=str(server),
        once=once,
        max_cycles=max_cycles,
        execute=execute,
    )
