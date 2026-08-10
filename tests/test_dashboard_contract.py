from __future__ import annotations

from pathlib import Path


def test_dashboard_does_not_call_legacy_chat_routes() -> None:
    static = Path("src/tianjun/interfaces/dashboard/static/js")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in static.rglob("*.js"))

    assert '"/intent"' not in combined
    assert '"/chat"' not in combined
    assert '"/hermes/' not in combined


def test_overview_resource_pool_displays_gpu_capacity() -> None:
    overview = Path("src/tianjun/interfaces/dashboard/static/js/pages/overview.js").read_text(encoding="utf-8")

    assert 'renderCapacityMetric("GPU", dc.gpu)' in overview
    assert "gpuCapacitySummary" in overview
    assert "任务槽位" not in overview


def test_topology_displays_gpu_capacity() -> None:
    topology = Path("src/tianjun/interfaces/dashboard/static/js/topology.js").read_text(encoding="utf-8")
    styles = Path("src/tianjun/interfaces/dashboard/static/css/pages/topology.css").read_text(encoding="utf-8")

    assert 'aggregateResources(nodes, "dc")' in topology
    assert "capacity?.gpu" in topology
    assert "GPU ${escapeHtml(gpu)}" in topology
    assert "node-gpu" not in topology
    assert ".node-gpu" not in styles
    assert topology.index('${detailRow("内存使用率", vm.memory)}') < topology.index("${gpuDetail}")
    assert 'const cpu = utilizationOf(actualNode, "cpu")' in topology
    assert "Math.min(92, Math.max(12" not in topology
    assert 'recommendedLabel = parsedRecommended?.vmIndex' in topology


def test_topology_vm_detail_keeps_display_id_in_sync_with_name() -> None:
    topology = Path("src/tianjun/interfaces/dashboard/static/js/topology.js").read_text(encoding="utf-8")
    topology_page = Path("src/tianjun/interfaces/dashboard/static/js/pages/topology.js").read_text(encoding="utf-8")

    assert '${detailRow("节点 ID", vm.name || "--")}' in topology
    assert '${detailRow("节点 ID", vm.nodeId || "--")}' not in topology
    assert "vmDisplayName(parsed.vmIndex, vmOrdinal)" in topology
    assert "vmDisplayName(parsedNode?.vmIndex, index + 1)" in topology
    assert "vmDisplayName(parsedRecommended.vmIndex)" in topology
    assert "parsedNode.vmIndex + 1" not in topology
    assert "parsedRecommended.vmIndex + 1" not in topology
    assert 'element.dataset.name ?? "VM-00"' in topology_page


def test_dashboard_tabs_expose_selected_state_and_controlled_panels() -> None:
    index = Path("src/tianjun/interfaces/dashboard/static/index.html").read_text(encoding="utf-8")
    router = Path("src/tianjun/interfaces/dashboard/static/js/router.js").read_text(encoding="utf-8")

    assert 'aria-selected="true" aria-controls="page-overview"' in index
    assert 'role="tabpanel" aria-labelledby="tab-overview"' in index
    assert 'button.setAttribute("aria-selected", String(selected))' in router
    assert "handleTabKeydown" in router


def test_dashboard_uses_bounded_views_and_non_overlapping_polling() -> None:
    api = Path("src/tianjun/interfaces/dashboard/static/js/api.js").read_text(encoding="utf-8")
    router = Path("src/tianjun/interfaces/dashboard/static/js/router.js").read_text(encoding="utf-8")

    assert 'fetchReport("summary"' in router
    assert 'fetchReport(page' in router
    assert 'setTimeout(() => void refreshDashboard()' in router
    assert "setInterval" not in router
    assert 'new AbortController()' in router
    assert 'document.addEventListener("visibilitychange"' in router
    assert '`/report/${encodeURIComponent(view)}${suffix}`' in api


def test_dashboard_exposes_hierarchical_batch_strategy_and_group_weights() -> None:
    scheduling = Path("src/tianjun/interfaces/dashboard/static/js/pages/scheduling.js").read_text(encoding="utf-8")
    model = Path("src/tianjun/interfaces/dashboard/static/js/pages/model.js").read_text(encoding="utf-8")

    assert "B6-hierarchical-batch" in scheduling
    assert "group_objective_breakdown" in scheduling
    assert "group_weights" in model
    assert "五类业务目标" in model
    assert "十维原子指标（解释、单目标与双目标消融）" in model
