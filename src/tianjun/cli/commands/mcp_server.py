from __future__ import annotations

import os
from argparse import Namespace

from tianjun.config import TianjunConfig, first_present


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    server = first_present(args.server, app_config.get("mcp.base_url"))
    if server:
        os.environ["TIANJUN_BASE_URL"] = str(server)
    from tianjun.integrations.mcp_server import main as mcp_main

    mcp_main()
