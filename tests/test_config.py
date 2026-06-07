from __future__ import annotations

from tianjun.config import TianjunConfig


def test_example_config_loads() -> None:
    config = TianjunConfig.load("configs/tianjun.example.toml")

    assert config.get("server.host") == "127.0.0.1"
    assert int(config.get("server.port")) == 8024
    assert config.get("llm.api_key_secret") == "llm.api_key"
