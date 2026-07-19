from __future__ import annotations

from pathlib import Path


def test_cloudsim_nodes_register_with_gpu_capacity() -> None:
    experiment = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java"
    ).read_text(encoding="utf-8")
    bridge = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java"
    ).read_text(encoding="utf-8")

    assert "gpuCapacityForNode" in experiment
    assert "final double gpuCount = gpuCapacityForNode(site, index);" in experiment
    assert '"labels": ["cloudsim", "cpu", "gpu", "%s", "latency-sensitive"]' in bridge


def test_cloudsim_gpu_tasks_and_resilient_lease_loop() -> None:
    experiment = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java"
    ).read_text(encoding="utf-8")
    bridge = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java"
    ).read_text(encoding="utf-8")

    assert "Tianjun lease polling failed" in experiment
    assert "executeExternalLease(lease, node, tick);" in experiment
    assert "reportResultWithRetry" in experiment
    assert "gpuAccelerated ? 1.0 : 0.0" in experiment
    assert '"labels": ["cloudsim", "cpu", "gpu", "%s", "latency-sensitive"]' in bridge


def test_cloudsim_example_has_fast_batch_and_listener_mode() -> None:
    experiment = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java"
    ).read_text(encoding="utf-8")
    bridge = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java"
    ).read_text(encoding="utf-8")

    assert "private static final double HEARTBEAT_INTERVAL_SECONDS = 2.0;" in experiment
    assert "private static final long LISTENER_POLL_MILLIS = 350L;" in experiment
    assert "8_000L + index % 6 * 2_000L" in experiment
    assert ".setBw(20_000L)" in experiment
    assert "final long bandwidthMbps = 120_000L;" in experiment
    assert "listenForExternalLeases" in experiment
    assert "executeExternalLease" in experiment
    assert "ESTIMATED_DURATION_PATTERN" in bridge
    assert "PREDICTED_COST_PATTERN" in bridge


def test_cloudsim_example_reports_incremental_operational_carbon() -> None:
    experiment = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java"
    ).read_text(encoding="utf-8")
    bridge = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java"
    ).read_text(encoding="utf-8")

    assert "PowerModelHostSimple" in experiment
    assert "computeCarbonG" in experiment
    assert "networkCarbonG" in experiment
    assert '"carbon_scope": "operational_only"' in bridge
    assert '"energy_kwh_delta"' in bridge
    assert '"carbon_intensity_g_per_kwh"' in bridge
    assert Path("examples/cloudsimplus/src/main/resources/tianjun-power-profiles.json").is_file()
    assert Path("examples/cloudsimplus/src/main/resources/tianjun-carbon-intensity-trace.csv").is_file()


def test_cloudsim_batch_bridge_uses_unified_resources_and_measured_metrics() -> None:
    experiment = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java"
    ).read_text(encoding="utf-8")
    bridge = Path(
        "examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java"
    ).read_text(encoding="utf-8")

    for resource in ("cpu", "memory", "gpu", "storage", "mips", "gpu_memory", "storage_iops", "bandwidth"):
        assert f'"{resource}"' in bridge
    assert "commitTaskBatch" in bridge
    assert '"jct_seconds"' in bridge
    assert '"cpu_utilization"' in bridge
    assert "getBatchActualMetrics" in bridge
    assert "loadPowerProfiles" in experiment
    assert "loadCarbonProfiles" in experiment
    assert "powerW * intervalSeconds / 3_600_000.0" in bridge
