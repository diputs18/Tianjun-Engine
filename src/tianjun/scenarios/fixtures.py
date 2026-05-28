from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain import (
    ExecutionMode,
    NetworkPathProfile,
    Node,
    ResourceVector,
    Task,
    TaskExecutionSpec,
    TaskStatus,
)


def load_scenario_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def node_from_dict(data: dict[str, Any]) -> Node:
    return Node(
        node_id=data["node_id"],
        region=data.get("region", "default"),
        location=data.get("location", data.get("region", "default")),
        service_region=data.get("service_region"),
        labels=set(data.get("labels", [])),
        capacity=ResourceVector(**data.get("capacity", {})),
        cost_per_tick=float(data.get("cost_per_tick", 1.0)),
        base_reliability=float(data.get("base_reliability", 0.98)),
        performance_factors={key: float(value) for key, value in data.get("performance_factors", {}).items()},
        health_score=float(data.get("health_score", 1.0)),
        reliability_score=data.get("reliability_score"),
        online=bool(data.get("online", True)),
        network_paths={
            str(region): NetworkPathProfile(**profile)
            for region, profile in data.get("network_paths", {}).items()
        },
    )


def task_from_dict(data: dict[str, Any]) -> Task:
    execution_data = data.get("execution")
    return Task(
        task_id=data["task_id"],
        task_type=data["task_type"],
        demand=ResourceVector(**data.get("demand", {})),
        estimated_duration=int(data.get("estimated_duration", 1)),
        priority=int(data.get("priority", 5)),
        budget=data.get("budget"),
        deadline=data.get("deadline"),
        data_region=data.get("data_region"),
        source_region=data.get("source_region"),
        input_size_gb=data.get("input_size_gb"),
        max_latency_ms=data.get("max_latency_ms"),
        min_bandwidth_mbps=data.get("min_bandwidth_mbps"),
        network_sensitivity=float(data.get("network_sensitivity", 0.5)),
        preferred_labels=set(data.get("preferred_labels", [])),
        security_level=str(data.get("security_level", "medium")),
        isolation_level=str(data.get("isolation_level", "process")),
        allowed_regions=set(data.get("allowed_regions", [])),
        forbidden_nodes=set(data.get("forbidden_nodes", [])),
        require_encrypted_transport=bool(data.get("require_encrypted_transport", True)),
        max_retries=int(data.get("max_retries", 1)),
        execution=None if execution_data is None else execution_from_dict(execution_data),
        submit_tick=int(data.get("submit_tick", 0)),
        status=TaskStatus(data.get("status", "pending")),
        attempts=int(data.get("attempts", 0)),
        last_scheduled_node=data.get("last_scheduled_node"),
        target_node_id=data.get("target_node_id"),
    )


def execution_from_dict(data: dict[str, Any]) -> TaskExecutionSpec:
    return TaskExecutionSpec(
        mode=ExecutionMode(data.get("mode", "noop")),
        command=list(data.get("command", [])),
        env={str(key): str(value) for key, value in data.get("env", {}).items()},
        workdir=data.get("workdir"),
        timeout_seconds=data.get("timeout_seconds"),
        shell=bool(data.get("shell", False)),
        image=data.get("image"),
        volumes=list(data.get("volumes", [])),
        namespace=str(data.get("namespace", "default")),
        job_name_prefix=str(data.get("job_name_prefix", "sched-agent")),
        cleanup=bool(data.get("cleanup", True)),
        image_pull_policy=data.get("image_pull_policy"),
        service_account_name=data.get("service_account_name"),
        labels={str(key): str(value) for key, value in data.get("labels", {}).items()},
        simulation=dict(data.get("simulation", {})),
    )


def scenario_nodes() -> list[Node]:
    return [
        Node(
            node_id="cpu-edge-sh-01",
            region="shanghai",
            labels={"cpu", "latency-sensitive"},
            capacity=ResourceVector(cpu=32, memory=96, gpu=0, storage=500),
            cost_per_tick=1.1,
            base_reliability=0.97,
            performance_factors={"batch_cpu": 1.3, "streaming": 1.15},
            network_paths={
                "shanghai": NetworkPathProfile(
                    latency_ms=9.0,
                    jitter_ms=1.8,
                    bandwidth_mbps=920.0,
                    bandwidth_jitter_mbps=55.0,
                    packet_loss=0.001,
                    path_reliability=0.996,
                ),
                "beijing": NetworkPathProfile(
                    latency_ms=32.0,
                    jitter_ms=8.0,
                    bandwidth_mbps=380.0,
                    bandwidth_jitter_mbps=120.0,
                    packet_loss=0.012,
                    path_reliability=0.956,
                ),
            },
        ),
        Node(
            node_id="mem-dense-sh-02",
            region="shanghai",
            labels={"cpu", "high-mem"},
            capacity=ResourceVector(cpu=24, memory=192, gpu=0, storage=800),
            cost_per_tick=1.4,
            base_reliability=0.98,
            performance_factors={"analytics": 1.45, "batch_cpu": 1.05},
            network_paths={
                "shanghai": NetworkPathProfile(
                    latency_ms=11.0,
                    jitter_ms=2.0,
                    bandwidth_mbps=860.0,
                    bandwidth_jitter_mbps=60.0,
                    packet_loss=0.002,
                    path_reliability=0.994,
                ),
                "beijing": NetworkPathProfile(
                    latency_ms=35.0,
                    jitter_ms=9.0,
                    bandwidth_mbps=340.0,
                    bandwidth_jitter_mbps=135.0,
                    packet_loss=0.014,
                    path_reliability=0.952,
                ),
            },
        ),
        Node(
            node_id="gpu-a100-sh-01",
            region="shanghai",
            labels={"gpu", "a100", "latency-sensitive"},
            capacity=ResourceVector(cpu=64, memory=256, gpu=4, storage=1000),
            cost_per_tick=4.8,
            base_reliability=0.985,
            performance_factors={"training": 2.4, "inference": 2.0},
            network_paths={
                "shanghai": NetworkPathProfile(
                    latency_ms=8.0,
                    jitter_ms=1.5,
                    bandwidth_mbps=980.0,
                    bandwidth_jitter_mbps=45.0,
                    packet_loss=0.001,
                    path_reliability=0.997,
                ),
                "beijing": NetworkPathProfile(
                    latency_ms=28.0,
                    jitter_ms=7.0,
                    bandwidth_mbps=420.0,
                    bandwidth_jitter_mbps=110.0,
                    packet_loss=0.010,
                    path_reliability=0.962,
                ),
            },
        ),
        Node(
            node_id="gpu-t4-bj-01",
            region="beijing",
            labels={"gpu", "t4"},
            capacity=ResourceVector(cpu=32, memory=128, gpu=2, storage=600),
            cost_per_tick=2.6,
            base_reliability=0.94,
            performance_factors={"training": 1.15, "inference": 1.35},
            network_paths={
                "beijing": NetworkPathProfile(
                    latency_ms=10.0,
                    jitter_ms=2.0,
                    bandwidth_mbps=760.0,
                    bandwidth_jitter_mbps=70.0,
                    packet_loss=0.003,
                    path_reliability=0.989,
                ),
                "shanghai": NetworkPathProfile(
                    latency_ms=31.0,
                    jitter_ms=11.0,
                    bandwidth_mbps=310.0,
                    bandwidth_jitter_mbps=140.0,
                    packet_loss=0.018,
                    path_reliability=0.944,
                ),
            },
        ),
    ]


def scenario_tasks() -> list[Task]:
    return [
        Task(
            task_id="task-train-001",
            task_type="training",
            demand=ResourceVector(cpu=16, memory=64, gpu=2, storage=120),
            estimated_duration=10,
            priority=10,
            budget=65.0,
            deadline=9,
            data_region="shanghai",
            source_region="shanghai",
            input_size_gb=6.0,
            min_bandwidth_mbps=220.0,
            network_sensitivity=0.7,
            preferred_labels={"gpu"},
            security_level="medium",
            allowed_regions={"shanghai"},
            max_retries=2,
        ),
        Task(
            task_id="task-infer-002",
            task_type="inference",
            demand=ResourceVector(cpu=8, memory=16, gpu=1, storage=40),
            estimated_duration=4,
            priority=9,
            budget=18.0,
            deadline=5,
            data_region="shanghai",
            source_region="shanghai",
            input_size_gb=1.5,
            max_latency_ms=25.0,
            min_bandwidth_mbps=180.0,
            network_sensitivity=0.92,
            preferred_labels={"gpu"},
            security_level="medium",
            allowed_regions={"shanghai"},
        ),
        Task(
            task_id="task-ana-003",
            task_type="analytics",
            demand=ResourceVector(cpu=12, memory=96, gpu=0, storage=80),
            estimated_duration=7,
            priority=7,
            budget=16.0,
            deadline=11,
            data_region="shanghai",
            source_region="shanghai",
            input_size_gb=4.0,
            min_bandwidth_mbps=140.0,
            network_sensitivity=0.55,
            preferred_labels={"high-mem"},
            security_level="medium",
            allowed_regions={"shanghai"},
        ),
        Task(
            task_id="task-stream-006",
            task_type="streaming",
            demand=ResourceVector(cpu=10, memory=20, gpu=0, storage=30),
            estimated_duration=3,
            priority=8,
            budget=7.0,
            deadline=6,
            data_region="shanghai",
            source_region="shanghai",
            input_size_gb=1.2,
            max_latency_ms=18.0,
            min_bandwidth_mbps=260.0,
            network_sensitivity=0.98,
            preferred_labels={"latency-sensitive"},
            security_level="medium",
            allowed_regions={"shanghai"},
        ),
    ]
