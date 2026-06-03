from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from tianjun.application.control_plane import CentralControlPlane
from tianjun.interfaces.http.server import build_http_server


class FakeChatRuntime:
    def __init__(self) -> None:
        self.commits: list[dict[str, Any]] = []

    def commit_session(self, session_id: str, policy_id: str | None = None) -> dict[str, Any]:
        self.commits.append({"session_id": session_id, "policy_id": policy_id})
        return {
            "status": "committed",
            "artifacts": {
                "commit": {
                    "status": "committed",
                    "policy": {"policy_id": policy_id or "policy-a"},
                },
            },
        }


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_chat_session_commit_requires_explicit_button_confirmation() -> None:
    chat = FakeChatRuntime()
    server = build_http_server(CentralControlPlane(), "127.0.0.1", 0, chat_runtime=chat)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        status, body = post_json(base_url, "/chat/sessions/session-a/commit", {"policy_id": "policy-a"})
        assert status == 403
        assert body == {"error": "chat policy commit requires explicit user button confirmation"}
        assert chat.commits == []

        status, body = post_json(
            base_url,
            "/chat/sessions/session-a/commit",
            {"policy_id": "policy-a", "confirmed_by_user_button": True},
        )
        assert status == 200
        assert body["status"] == "committed"
        assert chat.commits == [{"session_id": "session-a", "policy_id": "policy-a"}]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
