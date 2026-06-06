from __future__ import annotations

import json
from typing import Any

from ...application.control_plane import CentralControlPlane
from ...chat import ChatRuntime


def handle_legacy_get(handler: Any, path: str, control_plane: CentralControlPlane, chat: ChatRuntime) -> bool:
    if path == "/hermes/status":
        handler._write_json(
            200,
            {
                "status": "ok",
                "mode": "optimized_chat_runtime",
                "deprecated": True,
                "replacement": "/health",
                "chat_runtime": chat.describe(),
                "model_runtime": control_plane.scheduler.model_runtime.describe(),
            },
        )
        return True
    return False


def handle_legacy_post(
    handler: Any,
    path: str,
    payload: dict[str, Any],
    control_plane: CentralControlPlane,
    chat: ChatRuntime,
) -> bool:
    if path == "/intent":
        handler._write_json(200, _legacy_intent(control_plane, payload))
        return True
    if path == "/chat":
        session_id = payload.get("session_id")
        if session_id:
            result = chat.continue_session(str(session_id), str(payload.get("message", "")))
        else:
            result = chat.start(str(payload.get("message", "")))
        handler._write_json(200, result)
        return True
    if path == "/hermes/chat":
        message = str(payload.get("message", "")).strip()
        if not message:
            handler._write_json(400, {"error": "message is required"})
            return True
        result = chat.start(message)
        handler._write_json(
            200,
            {
                "status": "ok",
                "deprecated": True,
                "replacement": "/chat/sessions",
                "reply": result.get("message", ""),
                "raw": result,
            },
        )
        return True
    if path == "/hermes/chat/stream":
        message = str(payload.get("message", "")).strip()
        if not message:
            handler._write_json(400, {"error": "message is required"})
            return True
        _write_legacy_hermes_stream(
            handler,
            chat,
            message,
            session_id=payload.get("session_id"),
            dashboard_payload=lambda result: handler._dashboard_payload_from_chat_result(result),
        )
        return True
    return False


def _legacy_intent(control_plane: CentralControlPlane, payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    dry_run = bool(payload.get("dry_run", False))
    requirement = control_plane.parse_requirement(message, overrides=payload.get("overrides"))
    policy = control_plane.draft_policy(requirement, execution_payload=payload.get("execution"))
    policy_id = str(policy["policy_id"])
    task = control_plane.policy_tasks[policy_id]
    preview = control_plane.preview_task(task)
    submitted = None
    status = "preview"
    lease = None
    if not dry_run:
        committed = control_plane.commit_policy(policy_id)
        submitted = committed.get("submitted_task")
        status = committed.get("status", "committed")
    return {
        "status": status,
        "mode": "optimized_legacy_dashboard_gateway",
        "deprecated": True,
        "replacement": "/chat/sessions",
        "interpretation": {
            "requirement": requirement,
            "policy_id": policy_id,
            "questions": requirement.get("questions", []),
            "dialogue_status": requirement.get("dialogue_status"),
        },
        "task": task.to_dict(),
        "preview_decision": preview,
        "submitted_task": submitted,
        "lease": lease,
        "policy": policy,
        "hermes_tool_contract": {
            "endpoint": "/intent",
            "method": "POST",
            "payload": {"message": "natural language scheduling requirement", "dry_run": False},
            "purpose": "Deprecated compatibility gateway. New clients should use /chat/sessions.",
        },
    }


def _write_legacy_hermes_stream(
    handler: Any,
    chat: ChatRuntime,
    message: str,
    *,
    session_id: Any = None,
    dashboard_payload,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache, no-transform")
    handler.send_header("Connection", "close")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    def send(payload: dict[str, Any]) -> None:
        body = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        handler.wfile.write(body)
        handler.wfile.flush()

    assistant_was_streamed = False

    def emit(event: dict[str, Any]) -> None:
        nonlocal assistant_was_streamed
        event_type = str(event.get("type") or "")
        if event_type == "assistant_delta":
            assistant_was_streamed = True
            send({"type": "delta", "text": str(event.get("delta", ""))})
        elif event_type == "llm_start":
            send({"type": "delta", "text": "\n[LLM] analyzing user intent...\n"})
        elif event_type == "llm_done":
            send({"type": "delta", "text": "[LLM] intent fields checked by Tianjun.\n"})
        elif event_type == "llm_fallback":
            reason = str(event.get("reason") or "request was not completed")
            send({"type": "delta", "text": f"[LLM fallback] {reason}; local rules are used.\n"})
        elif event_type == "tool_start":
            send({"type": "delta", "text": f"\n[tool] {event.get('tool', '')} ...\n"})
        elif event_type in {"tool_done", "tool_result"}:
            send({"type": "delta", "text": f"\n[tool done] {event.get('summary', '')}\n"})
        elif event_type == "session":
            session = event.get("session") or {}
            send({"type": "session", "session_id": session.get("session_id")})

    try:
        if session_id:
            result = chat.continue_session(str(session_id), message, stream_emit=emit)
        else:
            result = chat.start(message, stream_emit=emit)
        session = result.get("session") or {}
        send(
            {
                "type": "result",
                "deprecated": True,
                "replacement": "/chat/sessions/stream",
                "session_id": session.get("session_id"),
                "action": result.get("action"),
                "commit_policy_id": result.get("commit_policy_id"),
                "dashboard_payload": dashboard_payload(result),
            }
        )
        if result and result.get("message") and not assistant_was_streamed:
            send({"type": "delta", "text": str(result.get("message"))})
        send({"type": "done"})
        handler.close_connection = True
    except Exception as exc:  # noqa: BLE001
        send({"type": "error", "error": str(exc)})
        send({"type": "done"})
        handler.close_connection = True
