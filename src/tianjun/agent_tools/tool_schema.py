from __future__ import annotations

from typing import Any

from ..tools import TOOL_NAMES, tianjun_tool_contract


def hermes_tool_contract() -> dict[str, Any]:
    """Backward-compatible alias for the unified Tianjun tool contract."""
    contract = tianjun_tool_contract()
    contract["contract"] = "tianjun.tools.v2"
    return contract
