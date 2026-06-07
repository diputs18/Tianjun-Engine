from __future__ import annotations

import inspect

from tianjun.integrations import mcp_server
from tianjun.tools import CHAT_TOOL_NAMES, MCP_TOOL_NAMES, TOOL_NAMES, tianjun_tool_contract


def test_tool_contract_marks_intent_analysis_internal() -> None:
    contract = tianjun_tool_contract()

    assert "analyze_user_intent" in contract["internal_tools"]
    assert "analyze_user_intent" not in contract["tools"]
    assert "analyze_user_intent" not in contract["mcp_tools"]
    assert set(CHAT_TOOL_NAMES).issubset(set(contract["mcp_tools"]))


def test_mcp_contract_matches_registered_function_names() -> None:
    source = inspect.getsource(mcp_server.create_mcp)
    registered = {
        line.strip().removeprefix("def ").split("(", 1)[0]
        for line in source.splitlines()
        if line.startswith("    def ")
    } - {"tool"}

    assert set(MCP_TOOL_NAMES) == registered
    assert set(TOOL_NAMES).issubset(set(MCP_TOOL_NAMES))
