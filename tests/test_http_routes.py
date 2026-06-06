from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Iterator

from tianjun.application.bootstrap import build_control_plane
from tianjun.chat import ChatRuntime
from tianjun.interfaces.http.server import build_http_server
from tianjun.llm import LLMSettings


@contextmanager
def running_server() -> Iterator[str]:
    control_plane = build_control_plane()
    chat = ChatRuntime.with_llm_settings(control_plane, LLMSettings(offline=True))
    server = build_http_server(control_plane, "127.0.0.1", 0, chat_runtime=chat)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get_json(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_status(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_official_health_report_dashboard_routes() -> None:
    with running_server() as base_url:
        assert get_json(base_url, "/health")["status"] == "ok"
        assert isinstance(get_json(base_url, "/report")["nodes"], list)
        with urllib.request.urlopen(f"{base_url}/dashboard", timeout=5) as response:
            body = response.read().decode("utf-8").lower()
        assert response.status == 200
        assert "<!doctype html>" in body


def test_official_chat_session_route_starts_session() -> None:
    with running_server() as base_url:
        result = post_json(base_url, "/chat/sessions", {"message": "hello"})

        assert "session" in result
        assert result["session"]["session_id"]


def test_legacy_routes_remain_available_and_marked_deprecated() -> None:
    with running_server() as base_url:
        status = get_json(base_url, "/hermes/status")
        hermes = post_json(base_url, "/hermes/chat", {"message": "hello"})
        chat = post_json(base_url, "/chat", {"message": "hello"})

        assert status["deprecated"] is True
        assert hermes["deprecated"] is True
        assert chat["session"]["session_id"]


def test_confirmation_boundaries_reject_missing_confirmation() -> None:
    with running_server() as base_url:
        policy_status, policy_payload = post_status(base_url, "/policies/commit", {"policy_id": "missing"})
        task_status, task_payload = post_status(base_url, "/tasks/task-1/schedule", {})
        weights_status, weights_payload = post_status(base_url, "/policy-weights", {"weights": {}})

        assert policy_status == 403
        assert "confirmation" in policy_payload["error"]
        assert task_status == 403
        assert "confirmation" in task_payload["error"]
        assert weights_status == 403
        assert "confirmation" in weights_payload["error"]
