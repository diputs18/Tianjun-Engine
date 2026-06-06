from __future__ import annotations

import subprocess
import sys


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "main.py", *args],
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_cli_help_lists_core_commands() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "serve" in result.stdout
    assert "llm-check" in result.stdout
    assert "mcp-server" in result.stdout


def test_cli_package_exposes_parser_module() -> None:
    from tianjun.cli.parser import create_parser

    parser = create_parser()

    assert "serve" in parser.format_help()


def test_llm_check_offline_skips_network() -> None:
    result = run_cli("llm-check", "--config", "configs/tianjun.example.toml", "--offline")

    assert result.returncode == 0
    assert '"status": "skipped"' in result.stdout
