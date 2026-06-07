from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from tianjun.config import TianjunConfig

from . import require_model, resolved_llm_settings, resolved_model_dir, resolved_path_setting


def load_cli_config(args: Namespace) -> TianjunConfig:
    return TianjunConfig.load(getattr(args, "config", None))


__all__ = [
    "Path",
    "TianjunConfig",
    "load_cli_config",
    "require_model",
    "resolved_llm_settings",
    "resolved_model_dir",
    "resolved_path_setting",
]
