from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from tianjun.config import TianjunConfig, config_bool, config_path, first_present
from tianjun.config.secrets import delete_secret, describe_secret, read_secret, secret_path_from_config, write_secret
from tianjun.chat import ChatRuntime
from tianjun.llm import LLMSettings
from tianjun.node_agent.runtime import LightweightNodeAgent
from tianjun.node_agent.clients import HttpControlPlaneClient
from tianjun.application.bootstrap import build_control_plane
from tianjun.interfaces.http.server import build_http_server
from tianjun.storage.sqlite_state_store import SQLiteStateStore
from tianjun.node_agent.real_probe import run_real_node_agent
from tianjun.observability.reporting import format_report
from tianjun.execution.runtime_demo import run_runtime_demo
from tianjun.scenarios import load_scenario_payload, node_from_dict, task_from_dict
from tianjun.domain import ExecutionMode
from tianjun.inventory import load_inventory_config
from tianjun.simulation import run_simulation_backend


def add_llm_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llm-base-url", help="OpenAI-compatible endpoint base URL, e.g. https://api.deepseek.com")
    parser.add_argument("--llm-model", help="Model name for Tianjun chat response generation.")
    parser.add_argument("--llm-api-key", help="Bearer token for the LLM endpoint. Prefer `tianjun secrets set ...` for local use, or DEEPSEEK_API_KEY in containers/CI.")
    parser.add_argument("--llm-timeout-seconds", type=float, help="LLM request timeout in seconds.")
    parser.add_argument("--offline", action="store_true", help="Explicitly disable the LLM layer for local-only development.")


def _env_value(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value if value not in (None, "") else None


def _key_from_configured_env(app_config: TianjunConfig) -> tuple[str | None, str | None]:
    env_name = str(first_present(app_config.get("llm.api_key_env"), default="DEEPSEEK_API_KEY"))
    value = _env_value(env_name)
    return (value, env_name) if value else (None, None)


def _key_from_configured_secret(app_config: TianjunConfig) -> tuple[str | None, str | None]:
    secret_path = secret_path_from_config(app_config.get("llm.secrets_file"))
    secret_key = str(first_present(app_config.get("llm.api_key_secret"), default="llm.api_key"))
    return read_secret(secret_path, key=secret_key)


def resolved_llm_settings(args: argparse.Namespace, app_config: TianjunConfig) -> LLMSettings:
    env_settings = LLMSettings.from_env()
    configured_key, configured_source = _key_from_configured_env(app_config)
    secret_key, secret_source = _key_from_configured_secret(app_config)
    cli_key = getattr(args, "llm_api_key", None)
    config_key = app_config.get("llm.api_key")
    # Priority: explicit CLI > per-user secrets file > configured env/.env > generic env > literal config.
    # The secrets file avoids platform-specific shell setup and prevents stale global env vars from winning.
    api_key = first_present(cli_key, secret_key, configured_key, env_settings.api_key, config_key)
    api_key_source = None
    if cli_key:
        api_key_source = "--llm-api-key"
    elif secret_key:
        api_key_source = secret_source
    elif configured_key:
        api_key_source = configured_source
    elif env_settings.api_key:
        api_key_source = env_settings.api_key_source
    elif config_key:
        api_key_source = "llm.api_key"
    offline = bool(
        getattr(args, "offline", False)
        or env_settings.offline
        or config_bool(app_config.get("llm.offline"), default=False)
    )
    return LLMSettings(
        base_url=first_present(getattr(args, "llm_base_url", None), env_settings.base_url, app_config.get("llm.base_url")),
        model=first_present(getattr(args, "llm_model", None), env_settings.model, app_config.get("llm.model")),
        api_key=api_key,
        api_key_source=api_key_source,
        timeout_seconds=float(first_present(getattr(args, "llm_timeout_seconds", None), env_settings.timeout_seconds, app_config.get("llm.timeout_seconds"), default=30.0)),
        temperature=float(first_present(app_config.get("llm.temperature"), default=0.2)),
        max_tokens=int(first_present(app_config.get("llm.max_tokens"), default=700)),
        required=config_bool(app_config.get("llm.required"), default=True) and not offline,
        offline=offline,
    )


def add_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-dir", type=Path, help="Directory containing trained model artifacts.")
    parser.add_argument(
        "--require-model",
        action="store_true",
        help="Fail fast if no trained model artifact can be loaded.",
    )


def resolved_model_dir(args: argparse.Namespace, app_config: TianjunConfig) -> Path | None:
    if getattr(args, "model_dir", None) is not None:
        return config_path(args.model_dir)
    return app_config.path("model.dir")


def require_model(args: argparse.Namespace, app_config: TianjunConfig) -> bool:
    return bool(getattr(args, "require_model", False) or config_bool(app_config.get("model.require"), default=False))


def resolved_path_setting(
    args_value: Path | str | None,
    app_config: TianjunConfig,
    *config_keys: str,
    default: str | None = None,
) -> Path | None:
    if args_value is not None:
        return config_path(args_value)
    for key in config_keys:
        if app_config.get(key) is not None:
            return app_config.path(key)
    return config_path(default) if default is not None else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute-network policy agent with control plane and node execution feedback."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    runtime_demo = subparsers.add_parser(
        "runtime-demo",
        help="Run the direct control-plane + node-agent runtime flow.",
    )
    runtime_demo.add_argument("--config", type=Path)
    runtime_demo.add_argument("--scenario", type=Path)
    runtime_demo.add_argument("--max-rounds", type=int)
    runtime_demo.add_argument("--json-out", type=Path)
    runtime_demo.add_argument("--state-db", type=Path)
    add_model_options(runtime_demo)

    serve = subparsers.add_parser("serve", help="Start the central control-plane HTTP server.")
    serve.add_argument("--config", type=Path)
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--scenario", type=Path, help="Optional demo scenario to preload. Omitted by default for a clean control plane.")
    serve.add_argument("--demo", action="store_true", help="Preload examples/runtime_scenario.json demo nodes and tasks.")
    serve.add_argument("--inventory", type=Path, help="Config-driven simulated inventory JSON/TOML/YAML to register at startup.")
    serve.add_argument("--default-execution-mode", choices=[item.value for item in ExecutionMode], help="Default execution mode for chat/policy-generated tasks when no explicit execution payload is provided.")
    serve.add_argument("--state-db", type=Path)
    serve.add_argument("--heartbeat-timeout-seconds", type=float)
    serve.add_argument("--policy-update-interval", type=int)
    add_model_options(serve)
    add_llm_options(serve)

    chat = subparsers.add_parser("chat", help="Run a local interactive Tianjun chat session over the control-plane logic.")
    chat.add_argument("--config", type=Path)
    chat.add_argument("--scenario", type=Path)
    add_model_options(chat)
    add_llm_options(chat)

    llm_check = subparsers.add_parser("llm-check", help="Check the configured OpenAI-compatible LLM endpoint and API key.")
    llm_check.add_argument("--config", type=Path)
    add_llm_options(llm_check)

    mcp_server = subparsers.add_parser("mcp-server", help="Expose Tianjun HTTP tools as a Hermes-compatible MCP server.")
    mcp_server.add_argument("--config", type=Path)
    mcp_server.add_argument("--server", default=None, help="Tianjun control-plane base URL. Defaults to --config mcp.base_url, TIANJUN_BASE_URL or http://127.0.0.1:8024.")

    agent = subparsers.add_parser("agent", help="Run a lightweight node agent against the HTTP server.")
    agent.add_argument("--config", type=Path)
    agent.add_argument("--server")
    agent.add_argument("--scenario", type=Path)
    agent.add_argument("--node-id")
    agent.add_argument("--max-cycles", type=int)
    agent.add_argument("--poll-interval", type=float)

    real_agent = subparsers.add_parser(
        "real-agent",
        help="Run a real node telemetry agent with resource and network probing.",
    )
    real_agent.add_argument("--config", type=Path)
    real_agent.add_argument("--server")
    real_agent.add_argument("--node-config", type=Path)
    real_agent.add_argument("--once", action="store_true")
    real_agent.add_argument("--max-cycles", type=int)
    real_agent.add_argument(
        "--execute",
        action="store_true",
        help="Allow this real node to request leases and execute assigned tasks. Disabled by default.",
    )

    sim_backend = subparsers.add_parser("sim-backend", help="Run config-driven simulated node agents against the control-plane HTTP server.")
    sim_backend.add_argument("--config", type=Path)
    sim_backend.add_argument("--server")
    sim_backend.add_argument("--inventory", type=Path, required=True, help="Simulation inventory/workload profile config, preferably JSON for dependency-free usage.")
    sim_backend.add_argument("--node-id", action="append", help="Limit simulation to one node id; repeat to include multiple nodes.")
    sim_backend.add_argument("--max-cycles", type=int, help="Stop after N runtime ticks. Omit for a long-running simulated node backend.")
    sim_backend.add_argument("--poll-interval", type=float)
    sim_backend.add_argument("--time-scale", type=float, help="Simulation acceleration factor. Smaller is faster; default comes from inventory or 0.08.")
    sim_backend.add_argument("--verbose", action="store_true", help="Print concise node/progress logs. Full JSON is not printed unless this command exits.")

    secrets = subparsers.add_parser("secrets", help="Manage cross-platform local secrets such as the DeepSeek API key.")
    secrets.add_argument("--config", type=Path)
    secrets_sub = secrets.add_subparsers(dest="secrets_command", required=True)
    secrets_set = secrets_sub.add_parser("set", help="Store the LLM API key in the per-user secrets file.")
    secrets_set.add_argument("provider", nargs="?", default="deepseek", help="Provider label. Currently used for display only; default: deepseek.")
    secrets_set.add_argument("--api-key", required=True, help="API key to store. It is written to the user-level secrets file, not to the project repo.")
    secrets_show = secrets_sub.add_parser("show", help="Show where the configured LLM API key will be read from, without printing the secret.")
    secrets_show.add_argument("provider", nargs="?", default="deepseek")
    secrets_path = secrets_sub.add_parser("path", help="Print the active secrets file path.")
    secrets_path.add_argument("provider", nargs="?", default="deepseek")
    secrets_remove = secrets_sub.add_parser("remove", help="Remove the stored LLM API key from the secrets file.")
    secrets_remove.add_argument("provider", nargs="?", default="deepseek")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    app_config = TianjunConfig.load(getattr(args, "config", None))

    if args.command == "secrets":
        secret_path = secret_path_from_config(app_config.get("llm.secrets_file"))
        secret_key = str(first_present(app_config.get("llm.api_key_secret"), default="llm.api_key"))
        if args.secrets_command == "set":
            written = write_secret(args.api_key, secret_path, key=secret_key)
            print(json.dumps({
                "status": "ok",
                "provider": args.provider,
                "path": str(written),
                "key": secret_key,
                "message": "API key stored in the user-level secrets file. The raw key was not printed.",
            }, ensure_ascii=False, indent=2))
            return
        if args.secrets_command == "show":
            settings = resolved_llm_settings(args, app_config)
            description = describe_secret(secret_path, key=secret_key)
            print(json.dumps({
                "provider": args.provider,
                "configured_secret": description,
                "effective_llm_key_source": settings.api_key_source,
                "effective_llm_key_present": bool(settings.api_key),
                "effective_llm_key_fingerprint": settings.key_fingerprint(),
            }, ensure_ascii=False, indent=2))
            return
        if args.secrets_command == "path":
            print(str(secret_path))
            return
        if args.secrets_command == "remove":
            removed = delete_secret(secret_path, key=secret_key)
            print(json.dumps({"status": "removed" if removed else "not_found", "path": str(secret_path), "key": secret_key}, ensure_ascii=False, indent=2))
            return

    if args.command == "runtime-demo":
        scenario = resolved_path_setting(
            args.scenario,
            app_config,
            "runtime_demo.scenario",
            "scenario.path",
            default="examples/runtime_scenario.json",
        )
        state_db = resolved_path_setting(args.state_db, app_config, "runtime_demo.state_db")
        max_rounds = int(first_present(args.max_rounds, app_config.get("runtime_demo.max_rounds"), default=40))
        payload = run_runtime_demo(
            scenario,
            max_rounds=max_rounds,
            state_db_path=state_db,
            model_dir=resolved_model_dir(args, app_config),
            require_model=require_model(args, app_config),
        )
        report = payload["report"]
        print(format_report(report))
        if args.json_out:
            args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return

    if args.command == "serve":
        host = str(first_present(args.host, app_config.get("server.host"), app_config.get("control_plane.host"), default="127.0.0.1"))
        port = int(first_present(args.port, app_config.get("server.port"), app_config.get("control_plane.port"), default=8024))
        scenario = resolved_path_setting(args.scenario, app_config, "server.scenario", "control_plane.scenario")
        if args.demo and scenario is None:
            scenario = config_path("examples/runtime_scenario.json")
        inventory = resolved_path_setting(args.inventory, app_config, "server.inventory", "simulation.inventory")
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
        if inventory:
            # Validate the inventory path/configuration, but do not register its
            # nodes here. The dashboard should discover resources only after the
            # CloudSimPlus/simulation backend reports them.
            load_inventory_config(inventory)
        if scenario and not control_plane.tasks:
            payload = load_scenario_payload(scenario)
            for node_data in payload.get("nodes", []):
                control_plane.register_node(node_from_dict(node_data))
            for task_data in payload.get("tasks", []):
                control_plane.submit_task(task_from_dict(task_data))
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
        return


    if args.command == "chat":
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
        return

    if args.command == "llm-check":
        from tianjun.llm import OpenAICompatibleClient

        settings = resolved_llm_settings(args, app_config)
        print(json.dumps(settings.describe(), ensure_ascii=False, indent=2))
        settings.validate_for_chat()
        if not settings.enabled():
            print(json.dumps({"status": "skipped", "reason": "LLM is offline or disabled."}, ensure_ascii=False, indent=2))
            return
        if "api.deepseek.com" in str(settings.base_url) and not settings.api_key:
            raise ValueError("DeepSeek API requires an API key. Run `tianjun secrets set deepseek --api-key YOUR_KEY`, or set DEEPSEEK_API_KEY in .env / process environment.")
        client = OpenAICompatibleClient(settings)
        reply = client.chat([
            {"role": "system", "content": "你是连接测试助手，只回复 OK。"},
            {"role": "user", "content": "请回复 OK"},
        ], timeout_seconds=min(10.0, settings.timeout_seconds))
        print(json.dumps({"status": "ok", "reply": reply}, ensure_ascii=False, indent=2))
        return

    if args.command == "mcp-server":
        server = first_present(args.server, app_config.get("mcp.base_url"))
        if server:
            os.environ["TIANJUN_BASE_URL"] = str(server)
        from tianjun.integrations.mcp_server import main as mcp_main

        mcp_main()
        return

    if args.command == "agent":
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
        return

    if args.command == "sim-backend":
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
        return

    if args.command == "real-agent":
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
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
