from __future__ import annotations

from argparse import Namespace

from tianjun.application.bootstrap import build_control_plane
from tianjun.chat import ChatRuntime
from tianjun.cli import require_model, resolved_llm_settings, resolved_model_dir, resolved_path_setting
from tianjun.config import TianjunConfig
from tianjun.scenarios import load_scenario_payload, node_from_dict


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    scenario = resolved_path_setting(args.scenario, app_config, "chat.scenario", "scenario.path")
    control_plane = build_control_plane(
        model_dir=resolved_model_dir(args, app_config),
        require_model=require_model(args, app_config),
    )
    if scenario:
        payload = load_scenario_payload(scenario)
        for node_data in payload.get("nodes", []):
            control_plane.register_node(node_from_dict(node_data))
    runtime = ChatRuntime.with_llm_settings(control_plane, resolved_llm_settings(args, app_config))
    print("Tianjun chat is ready. Type 'exit' to quit.")
    session_id = None
    while True:
        try:
            message = input("> ").strip()
        except EOFError:
            break
        if message.lower() in {"exit", "quit"}:
            break
        if not message:
            continue
        result = runtime.start(message) if session_id is None else runtime.continue_session(session_id, message)
        session_id = result["session"]["session_id"]
        print(result["message"])
