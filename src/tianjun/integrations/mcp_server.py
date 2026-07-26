from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from ..tools import MCP_TOOL_NAMES


@dataclass(frozen=True, slots=True)
class TianjunHttpClient:
    base_url: str
    timeout_seconds: float = 30.0
    auth_token: str | None = None

    @classmethod
    def from_env(cls) -> "TianjunHttpClient":
        return cls(
            base_url=os.environ.get("TIANJUN_BASE_URL", "http://127.0.0.1:8024"),
            timeout_seconds=float(os.environ.get("TIANJUN_MCP_TIMEOUT_SECONDS", "30")),
            auth_token=os.environ.get("TIANJUN_AUTH_TOKEN"),
        )

    def get(self, path: str, *, tool_name: str | None = None) -> dict[str, Any]:
        return self._request("GET", path, tool_name=tool_name)

    def post(self, path: str, payload: dict[str, Any] | None = None, *, tool_name: str | None = None) -> dict[str, Any]:
        return self._request("POST", path, payload or {}, tool_name=tool_name)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, tool_name: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if tool_name:
            headers["X-Tianjun-Caller"] = "external_mcp"
            headers["X-Tianjun-Tool"] = tool_name
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Tianjun HTTP {method} {path} failed with {exc.code}: {details}") from exc
        return json.loads(raw or "{}")


def hermes_mcp_config_example(
    *,
    python_executable: str = "python",
    tianjun_base_url: str = "http://127.0.0.1:8024",
) -> dict[str, Any]:
    """Return a minimal Hermes MCP stdio config with an explicit tool allowlist."""
    return {
        "mcp_servers": {
            "tianjun": {
                "command": python_executable,
                "args": ["-m", "tianjun.integrations.mcp_server"],
                "env": {"TIANJUN_BASE_URL": tianjun_base_url},
                "tools": {"include": list(MCP_TOOL_NAMES)},
            }
        }
    }


def create_mcp(client: TianjunHttpClient | None = None) -> Any:
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised by CLI in environments without optional dep
        raise RuntimeError("fastmcp is required for the MCP server. Install with: pip install -e '.[mcp]'") from exc

    http = client or TianjunHttpClient.from_env()
    mcp = FastMCP("tianjun-compute-network")

    def tool(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        return mcp.tool()(func)

    @tool
    def get_cluster_state() -> dict[str, Any]:
        """获取当前算力网络控制面状态、节点、任务、策略权重和模型状态。"""
        return http.get("/report", tool_name="get_cluster_state")

    @tool
    def start_chat_session(message: str) -> dict[str, Any]:
        """启动智能聊天会话。系统会自动澄清需求、生成策略、仿真并等待确认。"""
        return http.post("/chat/sessions", {"message": message}, tool_name="start_chat_session")

    @tool
    def continue_chat_session(session_id: str, message: str) -> dict[str, Any]:
        """继续智能聊天会话，可用于补充槽位或反馈优化。正式提交需调用 commit_policy(confirmed=true)。"""
        return http.post(
            f"/chat/sessions/{session_id}/messages",
            {"message": message},
            tool_name="continue_chat_session",
        )

    @tool
    def get_chat_session(session_id: str) -> dict[str, Any]:
        """读取智能聊天会话状态、消息历史、策略 ID 和待确认状态。"""
        return http.get(f"/chat/sessions/{session_id}", tool_name="get_chat_session")

    @tool
    def start_requirement_dialogue(message: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """启动结构化需求澄清，只返回槽位、问题和会话状态。"""
        return http.post(
            "/conversations/start",
            {"message": message, "overrides": overrides or {}},
            tool_name="start_requirement_dialogue",
        )

    @tool
    def continue_requirement_dialogue(
        session_id: str,
        message: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """继续结构化需求澄清，合并用户补充信息。"""
        return http.post(
            f"/conversations/{session_id}/continue",
            {"message": message, "overrides": overrides or {}},
            tool_name="continue_requirement_dialogue",
        )

    @tool
    def draft_compute_network_policy(session_id: str, execution: dict[str, Any] | None = None) -> dict[str, Any]:
        """基于已澄清需求生成算网策略草案。"""
        return http.post(
            f"/conversations/{session_id}/draft",
            {"execution": execution},
            tool_name="draft_compute_network_policy",
        )

    @tool
    def compare_policy_options(session_id: str, execution: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare multiple policy options for a completed requirement dialogue."""
        session = http.get(f"/conversations/{session_id}")
        requirement = session.get("requirement")
        if not isinstance(requirement, dict):
            raise RuntimeError(f"Requirement session {session_id} is not ready for policy comparison.")
        return http.post(
            "/policies/compare",
            {"requirement": requirement, "execution": execution},
            tool_name="compare_policy_options",
        )

    @tool
    def simulate_policy(policy_id: str) -> dict[str, Any]:
        """仿真策略，返回负载、时延、成本、服务质量、安全和诊断建议。"""
        return http.post("/policies/simulate", {"policy_id": policy_id}, tool_name="simulate_policy")

    @tool
    def explain_policy(policy_id: str) -> dict[str, Any]:
        """读取策略详情，用于向用户解释组件选择、预期效果和风险。"""
        return http.get(f"/policies/{policy_id}", tool_name="explain_policy")

    @tool
    def parse_user_feedback(policy_id: str, instruction: str) -> dict[str, Any]:
        """将用户自然语言反馈归一化为结构化反馈。"""
        return http.post(
            "/feedback/parse",
            {"policy_id": policy_id, "instruction": instruction},
            tool_name="parse_user_feedback",
        )

    @tool
    def optimize_policy_from_feedback(policy_id: str, instruction: str) -> dict[str, Any]:
        """根据用户反馈生成优化后的策略。"""
        return http.post(
            f"/policies/{policy_id}/optimize",
            {"instruction": instruction},
            tool_name="optimize_policy_from_feedback",
        )

    @tool
    def commit_policy(policy_id: str, confirmed: bool = False) -> dict[str, Any]:
        """提交策略。只有用户明确确认后才允许 confirmed=true。"""
        if not confirmed:
            return {
                "status": "need_confirmation",
                "policy_id": policy_id,
                "message": "提交会创建真实任务；请先向用户确认，再以 confirmed=true 调用。",
            }
        return http.post(
            "/policies/commit",
            {"policy_id": policy_id, "confirmed": True},
            tool_name="commit_policy",
        )

    @tool
    def schedule_pending_task(task_id: str, confirmed: bool = False) -> dict[str, Any]:
        """调度由 CloudSimPlus 等外部系统已提交的待调度任务。只有用户明确确认后才会创建 lease。"""
        if not confirmed:
            return {
                "status": "need_confirmation",
                "task_id": task_id,
                "message": "调度将为现有任务创建执行租约；请先向用户确认，再以 confirmed=true 调用。",
            }
        return http.post(
            f"/tasks/{task_id}/schedule",
            {"confirmed": True},
            tool_name="schedule_pending_task",
        )

    @tool
    def import_task_batch(
        batch_name: str,
        tasks: list[dict[str, Any]],
        client_batch_id: str = "",
        defaults: dict[str, Any] | None = None,
        batch_preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """导入并原子校验JSON批任务；不会立即调度或创建租约。"""
        return http.post("/task-batches/import", {
            "batch_name": batch_name,
            "client_batch_id": client_batch_id,
            "defaults": defaults or {},
            "batch_preferences": batch_preferences or {},
            "tasks": tasks,
        }, tool_name="import_task_batch")

    @tool
    def get_task_batch(batch_id: str) -> dict[str, Any]:
        """读取批次、任务、最近预演方案和执行状态。"""
        return http.get(f"/task-batches/{batch_id}", tool_name="get_task_batch")

    @tool
    def get_batch_actual_metrics(batch_id: str) -> dict[str, Any]:
        """Read measured JCT, makespan, utilization, energy and operational carbon for an executed batch."""
        return http.get(
            f"/task-batches/{batch_id}/metrics",
            tool_name="get_batch_actual_metrics",
        )

    @tool
    def preview_batch_schedule(batch_id: str, strategy: str = "B4-pareto-tchebycheff") -> dict[str, Any]:
        """联合预演整个批次，返回任务节点映射、碳排放、SLA和碎片指标。"""
        return http.post(f"/task-batches/{batch_id}/preview", {"strategy": strategy}, tool_name="preview_batch_schedule")

    @tool
    def compare_batch_strategies(batch_id: str, strategies: list[str] | None = None) -> dict[str, Any]:
        """比较B0、B1、B3和B4等批调度策略，不创建租约。"""
        return http.post(f"/task-batches/{batch_id}/compare", {"strategies": strategies or []}, tool_name="compare_batch_strategies")

    @tool
    def commit_batch_schedule(
        batch_id: str,
        plan_id: str,
        resource_snapshot_version: int,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """确认批方案。只有用户明确确认后才会原子预留资源并创建租约。"""
        if not confirmed:
            return {
                "status": "need_confirmation",
                "batch_id": batch_id,
                "plan_id": plan_id,
                "message": "批调度将创建多个执行租约；请先确认，再以 confirmed=true 调用。",
            }
        return http.post(f"/task-batches/{batch_id}/commit", {
            "plan_id": plan_id,
            "resource_snapshot_version": resource_snapshot_version,
            "confirmed": True,
        }, tool_name="commit_batch_schedule")

    return mcp


def main() -> None:
    create_mcp().run()


if __name__ == "__main__":
    main()
