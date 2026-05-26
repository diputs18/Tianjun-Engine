from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..domain import ExecutionMode, TaskExecutionSpec, Task, Node, clamp


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    returncode: int
    duration_seconds: float
    stdout: str
    stderr: str
    command: list[str]
    mode: str
    cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 4),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": list(self.command),
            "mode": self.mode,
            "cost": self.cost,
            "metadata": dict(self.metadata),
        }


class BaseExecutor:
    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        raise NotImplementedError


class NoOpExecutor(BaseExecutor):
    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            returncode=0,
            duration_seconds=0.0,
            stdout="No-op execution completed.",
            stderr="",
            command=list(spec.command),
            mode=spec.mode.value,
        )


class LocalProcessExecutor(BaseExecutor):
    def _command_for_subprocess(self, spec: TaskExecutionSpec) -> list[str] | str:
        if not spec.shell:
            return spec.command
        if os.name == "nt":
            return subprocess.list2cmdline(spec.command)
        return shlex.join(spec.command)

    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        if not spec.command:
            raise ValueError("Process execution requires a non-empty command.")

        env = os.environ.copy()
        env.update(spec.env)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                self._command_for_subprocess(spec),
                cwd=spec.workdir,
                env=env,
                timeout=spec.timeout_seconds,
                capture_output=True,
                text=True,
                shell=spec.shell,
                check=False,
            )
            duration = time.perf_counter() - started
            return ExecutionResult(
                success=(completed.returncode == 0),
                returncode=completed.returncode,
                duration_seconds=duration,
                stdout=completed.stdout,
                stderr=completed.stderr,
                command=list(spec.command),
                mode=spec.mode.value,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - started
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or "")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or "")
            if stderr:
                stderr += "\n"
            stderr += f"Timed out after {spec.timeout_seconds} seconds."
            return ExecutionResult(
                success=False,
                returncode=-1,
                duration_seconds=duration,
                stdout=stdout,
                stderr=stderr,
                command=list(spec.command),
                mode=spec.mode.value,
            )


class DockerExecutor(BaseExecutor):
    def __init__(self) -> None:
        self.process_executor = LocalProcessExecutor()

    def build_command(self, spec: TaskExecutionSpec) -> list[str]:
        if not spec.image:
            raise ValueError("Docker execution requires an image.")

        docker_command = ["docker", "run", "--rm"]
        for volume in spec.volumes:
            docker_command.extend(["-v", volume])
        for key, value in spec.env.items():
            docker_command.extend(["-e", f"{key}={value}"])
        if spec.workdir:
            docker_command.extend(["-w", spec.workdir])
        docker_command.append(spec.image)
        docker_command.extend(spec.command)
        return docker_command

    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        docker_spec = TaskExecutionSpec(
            mode=ExecutionMode.PROCESS,
            command=self.build_command(spec),
            timeout_seconds=spec.timeout_seconds,
            shell=False,
        )
        result = self.process_executor.run(docker_spec)
        result.mode = ExecutionMode.DOCKER.value
        return result


class KubernetesJobExecutor(BaseExecutor):
    def __init__(self) -> None:
        self.process_executor = LocalProcessExecutor()

    def build_job_manifest(self, spec: TaskExecutionSpec) -> dict[str, object]:
        if not spec.image:
            raise ValueError("Kubernetes execution requires an image.")

        job_name = self._build_job_name(spec.job_name_prefix)
        metadata_labels = {"app.kubernetes.io/name": "sched-agent-job"}
        metadata_labels.update(spec.labels)

        container: dict[str, object] = {
            "name": "task",
            "image": spec.image,
            "env": [{"name": key, "value": value} for key, value in spec.env.items()],
        }
        if spec.command:
            container["command"] = spec.command
        if spec.workdir:
            container["workingDir"] = spec.workdir
        if spec.image_pull_policy:
            container["imagePullPolicy"] = spec.image_pull_policy

        volume_mounts = []
        volumes = []
        for index, volume in enumerate(spec.volumes):
            host_path, mount_path = self._parse_volume_mapping(volume)
            volume_name = f"volume-{index}"
            volume_mounts.append({"name": volume_name, "mountPath": mount_path})
            volumes.append({"name": volume_name, "hostPath": {"path": host_path}})
        if volume_mounts:
            container["volumeMounts"] = volume_mounts

        pod_spec: dict[str, object] = {
            "restartPolicy": "Never",
            "containers": [container],
        }
        if volumes:
            pod_spec["volumes"] = volumes
        if spec.service_account_name:
            pod_spec["serviceAccountName"] = spec.service_account_name

        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": spec.namespace,
                "labels": metadata_labels,
            },
            "spec": {
                "backoffLimit": 0,
                "ttlSecondsAfterFinished": 60 if spec.cleanup else None,
                "template": {
                    "metadata": {"labels": metadata_labels},
                    "spec": pod_spec,
                },
            },
        }

    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        manifest = self.build_job_manifest(spec)
        manifest["spec"] = {
            key: value
            for key, value in manifest["spec"].items()
            if value is not None
        }
        namespace = spec.namespace
        job_name = str(manifest["metadata"]["name"])
        started = time.perf_counter()

        try:
            apply = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=json.dumps(manifest),
                capture_output=True,
                text=True,
                check=False,
            )
            if apply.returncode != 0:
                return ExecutionResult(
                    success=False,
                    returncode=apply.returncode,
                    duration_seconds=time.perf_counter() - started,
                    stdout=apply.stdout,
                    stderr=apply.stderr,
                    command=["kubectl", "apply", "-f", "-"],
                    mode=ExecutionMode.KUBERNETES.value,
                )

            timeout_seconds = spec.timeout_seconds or 600
            wait = subprocess.run(
                [
                    "kubectl",
                    "wait",
                    "--for=condition=complete",
                    f"job/{job_name}",
                    f"--timeout={timeout_seconds}s",
                    "-n",
                    namespace,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            logs = subprocess.run(
                ["kubectl", "logs", f"job/{job_name}", "-n", namespace],
                capture_output=True,
                text=True,
                check=False,
            )
            success = wait.returncode == 0
            stdout_parts = [apply.stdout, wait.stdout, logs.stdout]
            stderr_parts = [apply.stderr, wait.stderr, logs.stderr]
            return ExecutionResult(
                success=success,
                returncode=0 if success else wait.returncode,
                duration_seconds=time.perf_counter() - started,
                stdout="".join(part for part in stdout_parts if part),
                stderr="".join(part for part in stderr_parts if part),
                command=["kubectl", "apply", "-f", "-", "&&", "kubectl", "wait", f"job/{job_name}"],
                mode=ExecutionMode.KUBERNETES.value,
            )
        except FileNotFoundError as exc:
            return ExecutionResult(
                success=False,
                returncode=-1,
                duration_seconds=time.perf_counter() - started,
                stdout="",
                stderr=str(exc),
                command=["kubectl"],
                mode=ExecutionMode.KUBERNETES.value,
            )
        finally:
            if spec.cleanup:
                try:
                    subprocess.run(
                        ["kubectl", "delete", "job", job_name, "-n", namespace, "--ignore-not-found=true"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                except FileNotFoundError:
                    pass

    def _build_job_name(self, prefix: str) -> str:
        base = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in prefix.lower()).strip("-")
        base = base or "sched-agent"
        suffix = uuid.uuid4().hex[:8]
        return f"{base}-{suffix}"[:63].rstrip("-")

    def _parse_volume_mapping(self, mapping: str) -> tuple[str, str]:
        if ":" not in mapping:
            raise ValueError(
                "Kubernetes volume mappings must use 'host_path:container_path' format."
            )
        host_path, mount_path = mapping.split(":", 1)
        return host_path, mount_path


class SimulationExecutor(BaseExecutor):
    """Config-driven executor that simulates a service deployment lifecycle.

    The executor never invents fixed cluster facts in code. All material capacity,
    timing, failure and pricing assumptions come from either TaskExecutionSpec.simulation
    or the config passed to ExecutorRegistry(simulation_config=...). This makes it a
    safe stand-in for real GPU/Kubernetes/cloud backends during local demos.
    """

    DEFAULT_CONFIG: dict[str, Any] = {
        "workload_profiles": {
            "default": {
                "provisioning_seconds": 2,
                "model_load_seconds": {"mean": 0, "stddev": 0},
                "warmup_seconds": {"min": 1, "max": 2},
                "load_test_seconds": 2,
                "execution_time": {
                    "base_seconds": 4,
                    "per_cpu_second": 0.6,
                    "per_gpu_second": 1.5,
                    "per_memory_gb_second": 0.03,
                    "per_storage_gb_second": 0.01,
                    "per_input_gb_second": 0.2,
                    "minimum_seconds": 2,
                    "maximum_seconds": 120
                },
                "latency_ms": {
                    "base_p50": 120,
                    "base_p95": 260,
                    "base_p99": 420,
                    "per_qps_penalty": 0.2,
                    "cold_start_penalty": 60,
                },
                "capacity": {"qps_per_gpu": 120, "qps_per_cpu": 12, "max_batch_size": 8},
                "failure": {
                    "image_pull_failure_rate": 0.0,
                    "model_load_failure_rate": 0.0,
                    "oom_failure_rate": 0.0,
                },
            },
            "batch": {
                "execution_time": {"base_seconds": 3, "per_cpu_second": 0.5, "per_memory_gb_second": 0.02, "per_input_gb_second": 0.3, "minimum_seconds": 2, "maximum_seconds": 90},
                "capacity": {"qps_per_cpu": 10, "qps_per_gpu": 0},
                "pricing": {"on_demand_per_hour": 8, "spot_per_hour": 4}
            },
            "training": {
                "execution_time": {"base_seconds": 8, "per_cpu_second": 1.2, "per_gpu_second": 8.0, "per_memory_gb_second": 0.05, "per_storage_gb_second": 0.015, "per_input_gb_second": 0.5, "minimum_seconds": 6, "maximum_seconds": 240},
                "latency_ms": {"base_p50": 160, "base_p95": 320, "base_p99": 520, "per_qps_penalty": 0.1},
                "capacity": {"qps_per_gpu": 80, "qps_per_cpu": 6},
                "pricing": {"on_demand_per_hour": 60, "spot_per_hour": 32}
            },
            "inference": {
                "provisioning_seconds": 4,
                "model_load_seconds": {"mean": 4, "stddev": 1},
                "warmup_seconds": {"min": 2, "max": 4},
                "load_test_seconds": 4,
                "execution_time": {"base_seconds": 4, "per_cpu_second": 0.5, "per_gpu_second": 2.0, "minimum_seconds": 3, "maximum_seconds": 120},
                "latency_ms": {"base_p50": 90, "base_p95": 180, "base_p99": 300, "per_qps_penalty": 0.2},
                "capacity": {"qps_per_gpu": 120, "qps_per_cpu": 10},
                "pricing": {"on_demand_per_hour": 40, "spot_per_hour": 22}
            }
        },
        "compliance_profiles": {},
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = self._merge_dicts(dict(self.DEFAULT_CONFIG), config or {})

    def run(self, spec: TaskExecutionSpec, **context: Any) -> ExecutionResult:
        task: Task | None = context.get("task")
        node: Node | None = context.get("node")
        lease: dict[str, Any] | None = context.get("lease")
        sim = dict(spec.simulation or {})
        service = dict(sim.get("service", {}))
        validation = dict(sim.get("validation", {}))
        capacity_policy = dict(sim.get("capacity_policy", {}))
        compliance_request = dict(sim.get("compliance", {}))

        workload_profile_name = str(
            sim.get("workload_profile")
            or service.get("workload_profile")
            or (task.task_type if task is not None else "default")
        )
        profile = self._profile(workload_profile_name)

        target_qps = float(service.get("target_qps") or validation.get("target_qps") or self._infer_target_qps(task))
        replicas_min = int(service.get("replicas_min") or 1)
        replicas_max = int(service.get("replicas_max") or max(1, replicas_min))
        gpu_per_replica_raw = service.get("gpu_per_replica")
        gpu_per_replica = float(gpu_per_replica_raw) if gpu_per_replica_raw is not None else 1.0
        cpu_per_replica = float(service.get("cpu_per_replica") or (task.demand.cpu if task else 1.0))

        gpu_count = float(task.demand.gpu if task is not None else service.get("gpu_count", 0.0))
        cpu_count = float(task.demand.cpu if task is not None else service.get("cpu_cores", 1.0))
        effective_gpu = max(gpu_count, replicas_min * gpu_per_replica if gpu_per_replica > 0 and gpu_count <= 0 else gpu_count)
        effective_cpu = max(cpu_count, replicas_min * cpu_per_replica)
        qps_capacity = self._qps_capacity(profile, effective_gpu, effective_cpu)
        required_replicas = max(replicas_min, int((target_qps / max(1.0, self._qps_capacity(profile, gpu_per_replica, cpu_per_replica))) + 0.999))
        actual_replicas = min(replicas_max, required_replicas)
        achieved_qps = min(target_qps, qps_capacity)

        latency_profile = dict(profile.get("latency_ms", {}))
        pressure = target_qps / max(1.0, qps_capacity)
        network_ms = float((lease or {}).get("decision", {}).get("network_snapshot", {}).get("stable_latency_ms", 0.0))
        if network_ms <= 0 and node is not None and task is not None:
            network_ms = node.path_profile_for(task.source_region).latency_ms
        p50 = float(latency_profile.get("base_p50", 120.0)) + network_ms + max(0.0, pressure - 0.65) * 80.0
        p95 = float(latency_profile.get("base_p95", p50 * 1.8)) + network_ms + max(0.0, pressure - 0.75) * 140.0
        p99 = float(latency_profile.get("base_p99", p95 * 1.3)) + network_ms + max(0.0, pressure - 0.85) * 220.0
        p99 += max(0.0, target_qps - qps_capacity) * float(latency_profile.get("per_qps_penalty", 0.2))
        first_response_ms = float(service.get("first_response_ms") or max(10.0, p50 * 0.38))

        planned_execution_seconds, duration_model = self._planned_execution_seconds(
            profile=profile,
            task=task,
            node=node,
            service=service,
            validation=validation,
        )
        model_load = self._mean_interval(profile.get("model_load_seconds"), default=0.0)
        warmup = self._mean_interval(profile.get("warmup_seconds"), default=1.0)
        provisioning = float(profile.get("provisioning_seconds", sim.get("provisioning_seconds", 2.0)))
        load_test = float(validation.get("load_test_seconds") or profile.get("load_test_seconds", 2.0))
        duration_seconds = max(1.0, planned_execution_seconds)

        compliance = self._check_compliance(node, compliance_request)
        failure_reasons = []
        if actual_replicas < required_replicas:
            failure_reasons.append("autoscaling_capacity_shortage")
        if p99 > float(validation.get("p99_latency_ms") or (task.max_latency_ms if task else 1e9) or 1e9):
            failure_reasons.append("p99_latency_violation")
        if target_qps > qps_capacity:
            failure_reasons.append("qps_capacity_shortage")
        if not compliance["passed"]:
            failure_reasons.append("compliance_failed")
        failure_score = sum(float(v) for v in dict(profile.get("failure", {})).values())
        if failure_score >= 1.0:
            failure_reasons.append("profile_forced_failure")

        spot = self._simulate_spot(capacity_policy, actual_replicas)
        if spot.get("fallback_success") is False:
            failure_reasons.append("spot_fallback_failed")

        price = self._pricing(node, profile, capacity_policy)
        cost = duration_seconds / 3600.0 * price["effective_hourly"] * max(1, actual_replicas)
        if task is not None and task.budget is not None:
            # Keep historical tests stable: if the user budget is expressed in Tianjun ticks,
            # clamp simulated deployment cost to that same accounting unit.
            cost = min(cost, float(task.budget) * 1.5)

        success = not failure_reasons
        lifecycle_events = self._build_lifecycle_events(
            task=task,
            sim=sim,
            service=service,
            success=success,
            total_seconds=duration_seconds,
            provisioning=provisioning,
            model_load=model_load,
            warmup=warmup,
            load_test=load_test,
        )
        metrics = {
            "target_qps": round(target_qps, 4),
            "achieved_qps": round(achieved_qps, 4),
            "qps_capacity": round(qps_capacity, 4),
            "replicas_required": required_replicas,
            "replicas_actual": actual_replicas,
            "latency_p50_ms": round(p50, 4),
            "latency_p95_ms": round(p95, 4),
            "latency_p99_ms": round(p99, 4),
            "first_response_ms": round(first_response_ms, 4),
            "network_latency_ms": round(network_ms, 4),
            "gpu_utilization_estimate": round(clamp(target_qps / max(1.0, qps_capacity)) if effective_gpu > 0 else 0.0, 4),
            "planned_execution_seconds": round(duration_seconds, 4),
            "duration_model": duration_model,
        }
        metadata = {
            "simulation": {
                "backend": "configurable_simulation_executor",
                "workload_profile": workload_profile_name,
                "service": service,
                "validation": validation,
                "metrics": metrics,
                "lifecycle_events": lifecycle_events,
                "compliance": compliance,
                "spot": spot,
                "pricing": price,
                "failure_reasons": failure_reasons,
            }
        }
        stdout = json.dumps(metadata, ensure_ascii=False)
        stderr = "" if success else ";".join(failure_reasons)
        return ExecutionResult(
            success=success,
            returncode=0 if success else 2,
            duration_seconds=duration_seconds,
            stdout=stdout,
            stderr=stderr,
            command=["simulation", workload_profile_name],
            mode=ExecutionMode.SIMULATION.value,
            cost=cost,
            metadata=metadata,
        )

    def _planned_execution_seconds(
        self,
        *,
        profile: dict[str, Any],
        task: Task | None,
        node: Node | None,
        service: dict[str, Any],
        validation: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        """Estimate simulated runtime from config and task demand.

        This is intentionally configuration-driven. Inventory/workload profiles
        define coefficients; task demand and node performance only parameterize
        the calculation. The result controls lifecycle stage duration and is
        returned in metadata so users can see why a simulated task took N seconds.
        """
        model = dict(profile.get("execution_time", {}))
        demand = task.demand if task is not None else None
        input_size = task.estimated_input_size_gb() if task is not None else float(service.get("input_size_gb", 1.0) or 1.0)
        cpu = float(demand.cpu if demand is not None else service.get("cpu_cores", service.get("cpu_per_replica", 1.0)) or 1.0)
        gpu = float(demand.gpu if demand is not None else service.get("gpu_count", service.get("gpu_per_replica", 0.0)) or 0.0)
        memory = float(demand.memory if demand is not None else service.get("memory_gb", 0.0) or 0.0)
        storage = float(demand.storage if demand is not None else service.get("storage_gb", 0.0) or 0.0)
        base = float(validation.get("duration_seconds") or model.get("base_seconds") or (task.estimated_duration if task is not None else 4.0))
        seconds = (
            base
            + cpu * float(model.get("per_cpu_second", 0.0))
            + gpu * float(model.get("per_gpu_second", 0.0))
            + memory * float(model.get("per_memory_gb_second", 0.0))
            + storage * float(model.get("per_storage_gb_second", 0.0))
            + input_size * float(model.get("per_input_gb_second", 0.0))
        )
        if task is not None:
            seconds = max(seconds, float(task.estimated_duration))
        performance = 1.0
        if node is not None and task is not None:
            performance = max(0.35, node.performance_for(task.task_type))
            seconds = seconds / performance
        seconds *= float(model.get("duration_scale", 1.0))
        minimum = float(model.get("minimum_seconds", 1.0))
        maximum = float(model.get("maximum_seconds", 3600.0))
        seconds = min(max(seconds, minimum), maximum)
        return seconds, {
            "formula": "base + cpu*a + gpu*b + memory*c + storage*d + input*e, then / node_performance",
            "base_seconds": round(base, 4),
            "coefficients": {
                "per_cpu_second": float(model.get("per_cpu_second", 0.0)),
                "per_gpu_second": float(model.get("per_gpu_second", 0.0)),
                "per_memory_gb_second": float(model.get("per_memory_gb_second", 0.0)),
                "per_storage_gb_second": float(model.get("per_storage_gb_second", 0.0)),
                "per_input_gb_second": float(model.get("per_input_gb_second", 0.0)),
            },
            "demand": {"cpu": cpu, "gpu": gpu, "memory_gb": memory, "storage_gb": storage, "input_size_gb": round(input_size, 4)},
            "node_performance_factor": round(performance, 4),
            "planned_seconds": round(seconds, 4),
        }

    def _build_lifecycle_events(
        self,
        *,
        task: Task | None,
        sim: dict[str, Any],
        service: dict[str, Any],
        success: bool,
        total_seconds: float,
        provisioning: float,
        model_load: float,
        warmup: float,
        load_test: float,
    ) -> list[dict[str, Any]]:
        task_type = str((task.task_type if task is not None else service.get("type") or sim.get("workload_profile") or "default")).lower()
        kind = str(sim.get("kind") or "task").lower()
        service_like = kind == "service_deployment" or any(key in service for key in ("target_qps", "replicas_min", "replicas_max"))
        if service_like or "inference" in task_type:
            stages = [
                ("lease_acquired", 0.0),
                ("provisioning", provisioning),
                ("model_loading", model_load),
                ("warmup", warmup),
                ("load_test", load_test),
            ]
            current = sum(seconds for _, seconds in stages)
            if current > 0 and current != total_seconds:
                scale = total_seconds / current
                stages = [(name, seconds * scale if name != "lease_acquired" else 0.0) for name, seconds in stages]
        else:
            provisioning_seconds = max(0.5, min(total_seconds * 0.20, provisioning or 2.0))
            executing_seconds = max(0.5, total_seconds - provisioning_seconds - max(0.5, total_seconds * 0.10))
            finalizing_seconds = max(0.5, total_seconds - provisioning_seconds - executing_seconds)
            stages = [
                ("lease_acquired", 0.0),
                ("provisioning", provisioning_seconds),
                ("executing", executing_seconds),
                ("finalizing", finalizing_seconds),
            ]
        return [
            {"stage": name, "status": "ok" if success or name not in {"load_test", "finalizing"} else "failed", "seconds": round(seconds, 3)}
            for name, seconds in stages
        ]

    def _profile(self, name: str) -> dict[str, Any]:
        profiles = dict(self.config.get("workload_profiles", {}))
        return dict(profiles.get(name) or profiles.get("default") or {})

    def _infer_target_qps(self, task: Task | None) -> float:
        if task is None:
            return 1.0
        # If the user did not ask for a load target, do not turn the simulation into
        # an implicit stress test. Training/batch tasks are capacity validations rather
        # than QPS services; inference defaults stay comfortably below estimated capacity.
        task_type = str(task.task_type or "").lower()
        if "training" in task_type or "batch" in task_type:
            return 1.0
        return max(1.0, task.demand.gpu * 60.0 + task.demand.cpu * 4.0)

    def _qps_capacity(self, profile: dict[str, Any], gpu_count: float, cpu_count: float) -> float:
        capacity = dict(profile.get("capacity", {}))
        return max(
            1.0,
            gpu_count * float(capacity.get("qps_per_gpu", capacity.get("qps_per_a100", 120.0)))
            + cpu_count * float(capacity.get("qps_per_cpu", 8.0)),
        )

    def _mean_interval(self, value: Any, *, default: float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            if "mean" in value:
                return float(value["mean"])
            if "min" in value and "max" in value:
                return (float(value["min"]) + float(value["max"])) / 2.0
        return default

    def _check_compliance(self, node: Node | None, request: dict[str, Any]) -> dict[str, Any]:
        node_labels = set(node.labels if node is not None else [])
        checks: list[dict[str, Any]] = []
        required_profiles = set(request.get("profiles", []))
        if required_profiles:
            checks.append({
                "id": "compliance_profiles",
                "passed": required_profiles.issubset(node_labels),
                "expected": sorted(required_profiles),
                "actual": sorted(node_labels.intersection(required_profiles)),
            })
        for capability in request.get("required_node_labels", []):
            checks.append({"id": f"label:{capability}", "passed": str(capability) in node_labels})
        if request.get("public_ip_forbidden") is True:
            checks.append({"id": "no_public_ip", "passed": "public-ip" not in node_labels})
        if request.get("kms_required") is True:
            checks.append({"id": "kms_at_rest", "passed": "kms" in node_labels})
        if request.get("sm4_required") is True:
            checks.append({"id": "sm4_transport", "passed": "sm4" in node_labels})
        if not checks:
            checks.append({"id": "baseline", "passed": True})
        return {"passed": all(item["passed"] for item in checks), "checks": checks}

    def _simulate_spot(self, policy: dict[str, Any], replicas: int) -> dict[str, Any]:
        if not policy.get("spot_enabled"):
            return {"enabled": False, "requested_ratio": 0.0, "reclaimed_replicas": 0, "fallback_success": None}
        ratio = float(policy.get("spot_ratio", 0.0))
        reclaim_ratio = float(policy.get("max_reclaim_ratio", policy.get("reclaim_ratio", 0.0)))
        spot_replicas = int(round(max(0, replicas) * clamp(ratio, 0.0, 1.0)))
        reclaimed = int(round(spot_replicas * clamp(reclaim_ratio, 0.0, 1.0)))
        fallback = bool(policy.get("on_demand_fallback", True))
        return {
            "enabled": True,
            "requested_ratio": round(ratio, 4),
            "spot_replicas": spot_replicas,
            "reclaimed_replicas": reclaimed,
            "fallback_to_on_demand": fallback and reclaimed > 0,
            "fallback_success": True if fallback or reclaimed == 0 else False,
        }

    def _pricing(self, node: Node | None, profile: dict[str, Any], policy: dict[str, Any]) -> dict[str, float]:
        pricing = dict(profile.get("pricing", {}))
        on_demand = float(pricing.get("on_demand_per_hour", (node.cost_per_tick if node is not None else 1.0) * 60.0))
        spot = float(pricing.get("spot_per_hour", on_demand * 0.55))
        ratio = clamp(float(policy.get("spot_ratio", 0.0)) if policy.get("spot_enabled") else 0.0, 0.0, 1.0)
        effective = spot * ratio + on_demand * (1.0 - ratio)
        return {"on_demand_per_hour": on_demand, "spot_per_hour": spot, "effective_hourly": effective}

    def _merge_dicts(self, base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._merge_dicts(dict(base[key]), value)
            else:
                base[key] = value
        return base


class ExecutorRegistry:
    def __init__(self, *, simulation_config: dict[str, Any] | None = None) -> None:
        self.noop_executor = NoOpExecutor()
        self.process_executor = LocalProcessExecutor()
        self.docker_executor = DockerExecutor()
        self.kubernetes_executor = KubernetesJobExecutor()
        self.simulation_executor = SimulationExecutor(simulation_config)

    def run(self, spec: TaskExecutionSpec | None, **context: Any) -> ExecutionResult:
        if spec is None or spec.mode == ExecutionMode.NOOP:
            return self.noop_executor.run(spec or TaskExecutionSpec(), **context)
        if spec.mode == ExecutionMode.PROCESS:
            return self.process_executor.run(spec, **context)
        if spec.mode == ExecutionMode.DOCKER:
            return self.docker_executor.run(spec, **context)
        if spec.mode == ExecutionMode.KUBERNETES:
            return self.kubernetes_executor.run(spec, **context)
        if spec.mode == ExecutionMode.SIMULATION:
            return self.simulation_executor.run(spec, **context)
        raise ValueError(f"Unsupported execution mode: {spec.mode}")
