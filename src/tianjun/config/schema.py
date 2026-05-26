from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 8024,
        "state_db": None,
        "heartbeat_timeout_seconds": 15.0,
        "policy_update_interval": 2,
    },
    "scenario": {
        "path": None,
    },
    "model": {
        "dir": "${TIANJUN_HOME}/data/trained_models",
        # Predictive LSTM/GNN models are enabled when torch + artifacts are present.
        # They are non-fatal by default so the LLM-first chat/control-plane can start
        # on Windows/macOS/Linux without a platform-specific torch install.
        "require": False,
    },
    "llm": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_secret": "llm.api_key",
        "secrets_file": "${TIANJUN_CONFIG_DIR}/secrets.toml",
        "timeout_seconds": 30.0,
        "temperature": 0.2,
        "max_tokens": 700,
        "required": True,
        "offline": False,
    },
    "chat": {
        "require_llm": True,
        "scenario": None,
    },
    "mcp": {
        "base_url": "http://127.0.0.1:8024",
        "transport": "stdio",
    },
    "runtime_demo": {
        "scenario": None,
        "max_rounds": 40,
        "state_db": None,
    },
    "agent": {
        "server": None,
        "scenario": None,
        "node_id": None,
        "max_cycles": 30,
        "poll_interval_seconds": 1.0,
    },
    "real_agent": {
        "server": None,
        "node_config": None,
        "once": False,
        "execute": False,
        "max_cycles": None,
    },
    "security": {
        "require_commit_confirmation": True,
        "allow_process_executor": False,
        "allow_docker_executor": False,
        "allow_kubernetes_executor": False,
    },
}


@dataclass(frozen=True, slots=True)
class ConfigSource:
    path: str | None
    loaded: bool


def default_payload() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
