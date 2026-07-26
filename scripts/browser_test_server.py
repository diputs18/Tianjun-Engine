from __future__ import annotations

import os

from tianjun.application.bootstrap import build_control_plane
from tianjun.chat import ChatRuntime
from tianjun.interfaces.http.server import build_http_server
from tianjun.llm import LLMSettings
from tianjun.scenarios import scenario_nodes, scenario_tasks


def main() -> None:
    control = build_control_plane(heartbeat_timeout_seconds=3600.0)
    for node in scenario_nodes():
        control.register_node(node)
    for task in scenario_tasks():
        control.submit_task(task)
    chat = ChatRuntime.with_llm_settings(control, LLMSettings(offline=True))
    port = int(os.environ.get("PLAYWRIGHT_TEST_PORT", "8137"))
    server = build_http_server(
        control,
        "127.0.0.1",
        port,
        chat_runtime=chat,
        lifecycle_sweep_interval_seconds=5.0,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
