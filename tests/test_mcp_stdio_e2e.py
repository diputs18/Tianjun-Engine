from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tianjun.application.bootstrap import build_control_plane
from tianjun.chat import ChatRuntime
from tianjun.interfaces.http.server import build_http_server
from tianjun.llm import LLMSettings


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def running_control_plane():
    control = build_control_plane()
    chat = ChatRuntime.with_llm_settings(control, LLMSettings(offline=True))
    server = build_http_server(control, "127.0.0.1", 0, chat_runtime=chat)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def call_real_stdio_server(base_url: str) -> tuple[list[str], object]:
    environment = dict(os.environ)
    source_path = str(ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_path, environment.get("PYTHONPATH", "")) if item
    )
    environment["TIANJUN_BASE_URL"] = base_url
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tianjun.integrations.mcp_server"],
        env=environment,
        cwd=ROOT,
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("get_cluster_state", {})
            return [tool.name for tool in tools.tools], result


def get_report(base_url: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/report", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_real_stdio_mcp_call_updates_dashboard_success_state() -> None:
    with running_control_plane() as base_url:
        tool_names, result = asyncio.run(
            asyncio.wait_for(call_real_stdio_server(base_url), timeout=20)
        )

        assert "get_cluster_state" in tool_names
        assert result.isError is False
        report = get_report(base_url)
        runtime = report["toolchain_runtime"]
        assert runtime["external_mcp_call_count"] == 1
        assert runtime["external_mcp_success_count"] == 1
        assert runtime["external_mcp_last_success"]["tool_name"] == "get_cluster_state"
        assert runtime["external_mcp_last_success"]["result_status"] == "success"
