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
    assert topology.index('${detailRow("内存使用率", `${vm.memory}%`)}') < topology.index("${gpuDetail}")


def test_dashboard_exposes_hierarchical_batch_strategy_and_group_weights() -> None:
    scheduling = Path("src/tianjun/interfaces/dashboard/static/js/pages/scheduling.js").read_text(encoding="utf-8")
    model = Path("src/tianjun/interfaces/dashboard/static/js/pages/model.js").read_text(encoding="utf-8")

    assert "B6-hierarchical-batch" in scheduling
    assert "group_objective_breakdown" in scheduling
    assert "group_weights" in model
    assert "五类业务目标" in model
    assert "十维原子指标（解释、单目标与双目标消融）" in model
