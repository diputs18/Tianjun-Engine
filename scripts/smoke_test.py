from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def request_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str, timeout: float = 2.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def wait_for_health(base_url: str, deadline_seconds: float) -> dict:
    deadline = time.monotonic() + deadline_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return request_json(f"{base_url}/health")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"server did not become healthy: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Tianjun's minimal offline smoke test.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    state_directory = tempfile.TemporaryDirectory(prefix="tianjun-smoke-state-")
    command = [
        sys.executable,
        "-B",
        "main.py",
        "serve",
        "--config",
        "configs/tianjun.example.toml",
        "--offline",
        "--state-db",
        str(Path(state_directory.name) / "smoke.sqlite"),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        health = wait_for_health(base_url, args.timeout)
        report = request_json(f"{base_url}/report")
        dashboard = request_text(f"{base_url}/dashboard")

        from tianjun.tools import MCP_TOOL_NAMES, tianjun_tool_contract

        contract = tianjun_tool_contract()
        assert health["status"] == "ok"
        assert isinstance(report.get("nodes"), list)
        assert "<!doctype html>" in dashboard.lower()
        assert set(MCP_TOOL_NAMES).issubset(set(contract["mcp_tools"]))

        print(json.dumps({
            "status": "ok",
            "base_url": base_url,
            "health": health["status"],
            "nodes": len(report.get("nodes", [])),
            "mcp_tools": len(MCP_TOOL_NAMES),
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        state_directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
