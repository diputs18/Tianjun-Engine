from __future__ import annotations

import argparse
import os
import importlib
from pathlib import Path

from tianjun.config import TianjunConfig, config_bool, config_path, first_present
from tianjun.config.secrets import read_secret, secret_path_from_config
from tianjun.llm import LLMSettings
from tianjun.domain import ExecutionMode


COMMAND_HANDLERS = {
    "agent": "tianjun.cli.commands.agent",
    "chat": "tianjun.cli.commands.chat",
    "llm-check": "tianjun.cli.commands.llm_check",
    "mcp-server": "tianjun.cli.commands.mcp_server",
    "real-agent": "tianjun.cli.commands.real_agent",
    "runtime-demo": "tianjun.cli.commands.runtime_demo",
    "secrets": "tianjun.cli.commands.secrets",
    "serve": "tianjun.cli.commands.serve",
    "sim-backend": "tianjun.cli.commands.sim_backend",
}


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
    dispatch(args, app_config)


def dispatch(args: argparse.Namespace, app_config: TianjunConfig) -> None:
    module_name = COMMAND_HANDLERS.get(args.command)
    if module_name is None:
        raise ValueError(f"Unsupported command: {args.command}")
    module = importlib.import_module(module_name)
    module.handle(args, app_config)


if __name__ == "__main__":
    main()
