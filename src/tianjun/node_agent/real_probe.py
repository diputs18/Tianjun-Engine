from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .clients import HttpControlPlaneClient
from ..execution.executors import ExecutionResult, ExecutorRegistry
from ..domain import NetworkPathProfile, Node, ResourceVector, clamp
from ..scenarios import node_from_dict, task_from_dict


@dataclass(slots=True)
class ProbeTarget:
    name: str
    host: str
    region: str | None = None
    port: int | None = None


@dataclass(slots=True)
class RealNodeConfig:
    node: Node
    targets: list[ProbeTarget] = field(default_factory=list)
    heartbeat_interval_seconds: float = 5.0
    ping_count: int = 4
    ping_timeout_ms: int = 1200
    default_bandwidth_mbps: float = 1000.0
    allowed_execution_modes: set[str] = field(default_factory=lambda: {"noop"})
    max_tasks_per_cycle: int = 1


def load_real_node_config(path: str | Path) -> RealNodeConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    node = node_from_dict(payload["node"])
    execution = payload.get("execution", {})
    targets = [
        ProbeTarget(
            name=str(item.get("name") or item.get("region") or item["host"]),
            host=str(item["host"]),
            region=None if item.get("region") is None else str(item["region"]),
            port=None if item.get("port") is None else int(item["port"]),
        )
        for item in payload.get("probe_targets", [])
    ]
    return RealNodeConfig(
        node=node,
        targets=targets,
        heartbeat_interval_seconds=float(payload.get("heartbeat_interval_seconds", 5.0)),
        ping_count=int(payload.get("ping_count", 4)),
        ping_timeout_ms=int(payload.get("ping_timeout_ms", 1200)),
        default_bandwidth_mbps=float(payload.get("default_bandwidth_mbps", 1000.0)),
        allowed_execution_modes={str(item) for item in execution.get("allowed_modes", ["noop"])},
        max_tasks_per_cycle=max(1, int(execution.get("max_tasks_per_cycle", 1))),
    )


def detect_capacity(default: ResourceVector | None = None) -> ResourceVector:
    fallback = default or ResourceVector(cpu=2, memory=4, gpu=0, storage=40)
    cpu = float(os.cpu_count() or fallback.cpu)
    memory = _memory_gb() or fallback.memory
    storage = _storage_gb(Path.cwd()) or fallback.storage
    gpu = _gpu_count()
    return ResourceVector(cpu=cpu, memory=memory, gpu=float(gpu), storage=storage)


def collect_resource_health(node: Node) -> dict[str, Any]:
    cpu_util = _cpu_utilization()
    memory_util = _memory_utilization()
    disk_free_ratio = _disk_free_ratio(Path.cwd())
    pressure = max(cpu_util, memory_util, 1.0 - disk_free_ratio)
    health = clamp(1.0 - (pressure * 0.45), 0.35, 1.0)
    reliability = clamp((node.reliability_score or node.base_reliability) * (0.92 + (health * 0.08)), 0.35, 0.999)
    return {
        "health_score": health,
        "reliability_score": reliability,
        "local_resource_utilization": {
            "cpu": round(cpu_util, 4),
            "memory": round(memory_util, 4),
            "disk_used": round(1.0 - disk_free_ratio, 4),
        },
    }


def probe_network_paths(config: RealNodeConfig) -> dict[str, dict[str, float]]:
    paths: dict[str, dict[str, float]] = {}
    for target in config.targets:
        ping = ping_host(target.host, count=config.ping_count, timeout_ms=config.ping_timeout_ms)
        tcp_latency = tcp_probe_ms(target.host, target.port, timeout_ms=config.ping_timeout_ms) if target.port else None
        latency = ping["latency_ms"]
        if tcp_latency is not None and latency <= 0:
            latency = tcp_latency
        jitter = ping["jitter_ms"]
        packet_loss = ping["packet_loss"]
        reliability = clamp(1.0 - packet_loss)
        bandwidth = estimate_bandwidth_mbps(latency, jitter, packet_loss, config.default_bandwidth_mbps)
        profile = NetworkPathProfile(
            latency_ms=max(1.0, latency),
            jitter_ms=max(0.0, jitter),
            bandwidth_mbps=bandwidth,
            bandwidth_jitter_mbps=max(20.0, bandwidth * clamp(jitter / max(latency, 1.0), 0.02, 0.35)),
            packet_loss=packet_loss,
            path_reliability=reliability,
        )
        key = target.region or target.name
        paths[key] = profile.to_dict()
    return paths


def run_real_node_agent(
    config_path: str | Path,
    server: str,
    *,
    once: bool = False,
    max_cycles: int | None = None,
    execute: bool = False,
) -> None:
    config = load_real_node_config(config_path)
    config.node.capacity = detect_capacity(config.node.capacity)
    client = HttpControlPlaneClient(server)
    executors = ExecutorRegistry()
    client.register_node(config.node)

    cycles = 0
    while True:
        telemetry = collect_resource_health(config.node)
        network_paths = probe_network_paths(config)
        heartbeat_payload = {
            "health_score": telemetry["health_score"],
            "online": True,
            "cost_per_tick": config.node.cost_per_tick,
            "region": config.node.region,
            "labels": sorted(config.node.labels.union({"real-node"})),
            "performance_factors": dict(config.node.performance_factors),
            "network_paths": network_paths,
        }
        client.heartbeat(config.node.node_id, **heartbeat_payload)
        executed_tasks = []
        if execute:
            for _ in range(config.max_tasks_per_cycle):
                outcome = execute_assigned_task(
                    client,
                    config.node.node_id,
                    allowed_modes=config.allowed_execution_modes,
                    executors=executors,
                )
                if outcome is None:
                    break
                executed_tasks.append(outcome)
        cycles += 1
        print(
            json.dumps(
                {
                    "node_id": config.node.node_id,
                    "cycle": cycles,
                    "health_score": round(float(telemetry["health_score"]), 4),
                    "execution_enabled": execute,
                    "executed_tasks": executed_tasks,
                    "network_paths": network_paths,
                    "resource": telemetry["local_resource_utilization"],
                },
                ensure_ascii=False,
            )
        )
        if once or (max_cycles is not None and cycles >= max_cycles):
            return
        time.sleep(config.heartbeat_interval_seconds)


def execute_assigned_task(
    client: HttpControlPlaneClient,
    node_id: str,
    *,
    allowed_modes: set[str],
    executors: ExecutorRegistry,
) -> dict[str, Any] | None:
    lease = client.request_lease(node_id)
    if lease is None:
        return None

    task = task_from_dict(lease["task"])
    mode = task.execution.mode.value if task.execution is not None else "noop"
    if mode not in allowed_modes:
        result = ExecutionResult(
            success=False,
            returncode=-2,
            duration_seconds=0.0,
            stdout="",
            stderr=f"Execution mode '{mode}' is not allowed on real node '{node_id}'.",
            command=list(task.execution.command) if task.execution is not None else [],
            mode=mode,
        )
    else:
        result = executors.run(task.execution)
    record = client.report_result(node_id, task.task_id, result)
    return {
        "task_id": task.task_id,
        "mode": mode,
        "success": result.success,
        "returncode": result.returncode,
        "record_status": record.get("status"),
    }


def ping_host(host: str, *, count: int, timeout_ms: int) -> dict[str, float]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
    else:
        timeout_sec = max(1, int(round(timeout_ms / 1000)))
        cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding=None if system == "windows" else "utf-8",
            errors="ignore",
            timeout=max(3, count + 3),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"latency_ms": float(timeout_ms), "jitter_ms": float(timeout_ms) * 0.25, "packet_loss": 1.0}
    output = result.stdout + "\n" + result.stderr
    output = output.replace("时间", "time").replace("平均", "Average").replace("丢失", "loss")
    times = [float(item) for item in re.findall(r"(?:time[=<]|时间[=<])\s*([0-9.]+)\s*ms", output, flags=re.IGNORECASE)]
    if not times:
        times = [float(item) for item in re.findall(r"Average\s*=\s*([0-9.]+)ms", output, flags=re.IGNORECASE)]
    transmitted = count
    received = len(times)
    loss_match = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|丢失)", output, flags=re.IGNORECASE)
    packet_loss = float(loss_match.group(1)) / 100.0 if loss_match else clamp(1.0 - (received / max(1, transmitted)))
    if not times:
        return {"latency_ms": float(timeout_ms), "jitter_ms": float(timeout_ms) * 0.25, "packet_loss": packet_loss}
    return {
        "latency_ms": float(statistics.mean(times)),
        "jitter_ms": float(statistics.pstdev(times)) if len(times) > 1 else 0.0,
        "packet_loss": clamp(packet_loss),
    }


def tcp_probe_ms(host: str, port: int | None, *, timeout_ms: int) -> float | None:
    if port is None:
        return None
    start = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.2, timeout_ms / 1000.0)):
            return (time.perf_counter() - start) * 1000.0
    except OSError:
        return None


def estimate_bandwidth_mbps(latency_ms: float, jitter_ms: float, packet_loss: float, default_bandwidth: float) -> float:
    latency_penalty = clamp((latency_ms - 5.0) / 180.0)
    jitter_penalty = clamp(jitter_ms / max(5.0, latency_ms))
    loss_penalty = clamp(packet_loss / 0.08)
    quality = clamp(1.0 - ((latency_penalty * 0.25) + (jitter_penalty * 0.35) + (loss_penalty * 0.40)), 0.08, 1.0)
    return max(10.0, default_bandwidth * quality)


def _memory_gb() -> float | None:
    if platform.system().lower() == "windows":
        try:
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                text=True,
                timeout=5,
            )
            return round(float(output.strip()) / (1024**3), 2)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    try:
        data = Path("/proc/meminfo").read_text(encoding="utf-8")
        match = re.search(r"MemTotal:\s+(\d+)\s+kB", data)
        return round(float(match.group(1)) / (1024**2), 2) if match else None
    except OSError:
        return None


def _storage_gb(path: Path) -> float | None:
    try:
        usage = shutil.disk_usage(path)
        return round(float(usage.total) / (1024**3), 2)
    except OSError:
        return None


def _disk_free_ratio(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path)
        return clamp(usage.free / max(1, usage.total))
    except OSError:
        return 0.5


def _gpu_count() -> int:
    if shutil.which("nvidia-smi") is None:
        return 0
    try:
        output = subprocess.check_output(["nvidia-smi", "-L"], text=True, timeout=5, stderr=subprocess.DEVNULL)
        return len([line for line in output.splitlines() if line.strip().startswith("GPU ")])
    except (OSError, subprocess.SubprocessError):
        return 0


def _cpu_utilization() -> float:
    if platform.system().lower() == "windows":
        try:
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
                text=True,
                timeout=5,
            )
            return clamp(float(output.strip()) / 100.0)
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0.0
    try:
        first = _read_proc_stat()
        time.sleep(0.1)
        second = _read_proc_stat()
        if first is None or second is None:
            return 0.0
        idle_delta = second["idle"] - first["idle"]
        total_delta = second["total"] - first["total"]
        return clamp(1.0 - (idle_delta / max(1.0, total_delta)))
    except OSError:
        return 0.0


def _read_proc_stat() -> dict[str, float] | None:
    try:
        parts = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [float(item) for item in parts]
        idle = values[3] + (values[4] if len(values) > 4 else 0.0)
        return {"idle": idle, "total": sum(values)}
    except (OSError, IndexError, ValueError):
        return None


def _memory_utilization() -> float:
    if platform.system().lower() == "windows":
        try:
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem | ForEach-Object { 1 - ($_.FreePhysicalMemory / $_.TotalVisibleMemorySize) })"],
                text=True,
                timeout=5,
            )
            return clamp(float(output.strip()))
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0.0
    try:
        data = Path("/proc/meminfo").read_text(encoding="utf-8")
        total = float(re.search(r"MemTotal:\s+(\d+)\s+kB", data).group(1))  # type: ignore[union-attr]
        available = float(re.search(r"MemAvailable:\s+(\d+)\s+kB", data).group(1))  # type: ignore[union-attr]
        return clamp(1.0 - (available / max(1.0, total)))
    except (OSError, AttributeError, ValueError):
        return 0.0
