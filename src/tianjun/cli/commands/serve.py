from __future__ import annotations

from argparse import Namespace

from tianjun.application.bootstrap import build_control_plane
from tianjun.chat import ChatRuntime
from tianjun.config import TianjunConfig, first_present
from tianjun.domain import ExecutionMode
from tianjun.interfaces.http.server import build_http_server
from tianjun.scenarios import load_scenario_payload, node_from_dict, scenario_nodes, scenario_tasks, task_from_dict
from tianjun.storage.sqlite_state_store import SQLiteStateStore
from tianjun.cli import require_model, resolved_llm_settings, resolved_model_dir, resolved_path_setting


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    host = str(first_present(args.host, app_config.get("server.host"), app_config.get("control_plane.host"), default="127.0.0.1"))
    port = int(first_present(args.port, app_config.get("server.port"), app_config.get("control_plane.port"), default=8024))
    scenario = resolved_path_setting(args.scenario, app_config, "server.scenario", "control_plane.scenario")
    use_builtin_demo = bool(args.demo and scenario is None)
    state_db = resolved_path_setting(args.state_db, app_config, "server.state_db", "control_plane.state_db")
    heartbeat_timeout = float(first_present(
        args.heartbeat_timeout_seconds,
        app_config.get("server.heartbeat_timeout_seconds"),
        app_config.get("control_plane.heartbeat_timeout_seconds"),
        default=15.0,
    ))
    policy_update_interval = int(first_present(
        args.policy_update_interval,
        app_config.get("server.policy_update_interval"),
        app_config.get("control_plane.policy_update_interval"),
        default=2,
    ))
    state_store = None if state_db is None else SQLiteStateStore(state_db)
    control_plane = build_control_plane(
        state_store=state_store,
        heartbeat_timeout_seconds=heartbeat_timeout,
        policy_update_interval=policy_update_interval,
        model_dir=resolved_model_dir(args, app_config),
        require_model=require_model(args, app_config),
    )
    default_execution_mode = first_present(args.default_execution_mode, app_config.get("server.default_execution_mode"), app_config.get("simulation.default_execution_mode"))
    if default_execution_mode:
        control_plane.policy_generator.default_execution_mode = ExecutionMode(str(default_execution_mode))
    if scenario and not control_plane.tasks:
        payload = load_scenario_payload(scenario)
        for node_data in payload.get("nodes", []):
            control_plane.register_node(node_from_dict(node_data))
        for task_data in payload.get("tasks", []):
            control_plane.submit_task(task_from_dict(task_data))
    elif use_builtin_demo and not control_plane.tasks:
        for node in scenario_nodes():
            control_plane.register_node(node)
        for task in scenario_tasks():
            control_plane.submit_task(task)
    chat_runtime = ChatRuntime.with_llm_settings(control_plane, resolved_llm_settings(args, app_config))
    server = build_http_server(control_plane, host, port, chat_runtime=chat_runtime)
    print(f"Control plane listening on http://{host}:{port}")
    print(f"Dashboard available at http://{host}:{port}/dashboard")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if state_store is not None:
            state_store.close()
