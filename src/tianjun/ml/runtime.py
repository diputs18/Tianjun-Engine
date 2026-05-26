from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ..domain import NetworkPathProfile, Node, Task, clamp

# The control plane invokes model inference from HTTP worker threads during tests
# and demos. Keep BLAS/Torch pools small unless an operator opts into more
# parallelism; this avoids leaked non-daemon worker pools in short-lived runs.
os.environ.setdefault("OMP_NUM_THREADS", os.getenv("TIANJUN_TORCH_THREADS", "1"))
os.environ.setdefault("MKL_NUM_THREADS", os.getenv("TIANJUN_TORCH_THREADS", "1"))


def _configure_torch_runtime(torch: Any) -> None:
    """Keep control-plane inference deterministic and safe in request threads."""
    try:
        threads = max(1, int(os.getenv("TIANJUN_TORCH_THREADS", "1")))
    except ValueError:
        threads = 1
    try:
        torch.set_num_threads(threads)
    except Exception:
        pass
    try:
        torch.set_num_interop_threads(max(1, int(os.getenv("TIANJUN_TORCH_INTEROP_THREADS", "1"))))
    except Exception:
        pass


MODEL_DIR_ENV_VAR = "TIANJUN_MODEL_DIR"
DEFAULT_MODEL_DIR = Path("data") / "trained_models"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_FILES = {
    "lstm": "lstm_latency_model.pt",
    "gnn": "graphsage_stability_model.pt",
}
GNN_MAX_FEATURE_Z = 8.0


def _load_checkpoint_safely(torch: Any, path: Path, *, required_keys: set[str]) -> dict[str, Any]:
    """Load tensor checkpoints without allowing arbitrary pickle object execution."""
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise RuntimeError(
            "Secure model loading requires a PyTorch version supporting weights_only=True."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid model checkpoint at {path}: expected a dictionary payload.")
    missing = sorted(required_keys.difference(payload))
    if missing:
        raise ValueError(f"Invalid model checkpoint at {path}: missing keys {missing}.")
    return payload


def resolve_model_dir(model_dir: str | Path | None = None) -> Path:
    """Resolve the trained-model directory from explicit input, env, or the repo root."""
    raw = model_dir or os.getenv(MODEL_DIR_ENV_VAR)
    path = Path(raw) if raw else PROJECT_ROOT / DEFAULT_MODEL_DIR
    return path.expanduser().resolve()


@dataclass(frozen=True)
class ModelPrediction:
    enabled: bool
    lstm_latency_ms: float | None = None
    gnn_latency_ms: float | None = None
    gnn_stability_score: float | None = None
    gnn_raw_output: float | None = None
    gnn_applicable: bool | None = None
    gnn_diagnostic: str | None = None
    gnn_feature_shift: dict[str, Any] | None = None
    status: str = "not_loaded"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "lstm_latency_ms": self.lstm_latency_ms,
            "gnn_latency_ms": self.gnn_latency_ms,
            "gnn_stability_score": self.gnn_stability_score,
            "gnn_raw_output": self.gnn_raw_output,
            "gnn_applicable": self.gnn_applicable,
            "gnn_diagnostic": self.gnn_diagnostic,
            "gnn_feature_shift": self.gnn_feature_shift,
            "status": self.status,
            "detail": self.detail,
        }


class LstmLatencyModel:  # Lazy torch wrapper; importing this module remains cheap without torch.
    def __init__(self, path: Path) -> None:
        import torch
        from torch import nn

        _configure_torch_runtime(torch)

        class LatencyLSTM(nn.Module):
            def __init__(self, input_size: int, hidden_size: int) -> None:
                super().__init__()
                self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size, batch_first=True)
                self.head = nn.Sequential(
                    nn.Linear(hidden_size, hidden_size),
                    nn.ReLU(),
                    nn.Linear(hidden_size, 1),
                )

            def forward(self, x: Any) -> Any:
                output, _ = self.lstm(x)
                return self.head(output[:, -1, :]).squeeze(-1)

        self.torch = torch
        payload = _load_checkpoint_safely(torch, path, required_keys={"scaler", "model_state"})
        self.window = int(payload.get("window", 2))
        self.scaler = payload["scaler"]
        self.model = LatencyLSTM(
            input_size=int(payload.get("input_size", 2)),
            hidden_size=int(payload.get("hidden_size", 64)),
        )
        self.model.load_state_dict(payload["model_state"])
        self.model.eval()

    def predict(
        self,
        latency_history_ms: list[float],
        pressure_history: list[float],
        cpu_history: list[float] | None = None,
        memory_history: list[float] | None = None,
    ) -> float:
        torch = self.torch
        latencies = latency_history_ms[-self.window :]
        pressures = pressure_history[-self.window :]
        cpu_values = (cpu_history or [0.0])[-self.window :]
        memory_values = (memory_history or [0.0])[-self.window :]
        if len(latencies) < self.window:
            latencies = ([latencies[0] if latencies else 1.0] * (self.window - len(latencies))) + latencies
        if len(pressures) < self.window:
            pressures = ([pressures[0] if pressures else 0.0] * (self.window - len(pressures))) + pressures
        if len(cpu_values) < self.window:
            cpu_values = ([cpu_values[0] if cpu_values else 0.0] * (self.window - len(cpu_values))) + cpu_values
        if len(memory_values) < self.window:
            memory_values = ([memory_values[0] if memory_values else 0.0] * (self.window - len(memory_values))) + memory_values
        sequence = []
        for latency, pressure, cpu, memory in zip(latencies, pressures, cpu_values, memory_values):
            row = [math.log1p(max(0.0, latency)), math.log1p(max(0.0, pressure))]
            if int(getattr(self.model.lstm, "input_size", 2)) >= 4:
                row.extend([clamp(cpu), clamp(memory)])
            sequence.append(row)
        mean_values = self.scaler["mean"]
        std_values = self.scaler["std"]
        normalized = [
            [
                (value - mean_values[index]) / (std_values[index] or 1.0)
                for index, value in enumerate(row)
            ]
            for row in sequence
        ]
        with torch.no_grad():
            tensor = torch.tensor([normalized], dtype=torch.float32)
            pred_log = float(self.model(tensor).item())
        return max(1.0, math.expm1(pred_log))


class GraphSageStabilityModel:
    def __init__(self, path: Path) -> None:
        import torch
        from torch import nn

        _configure_torch_runtime(torch)

        class GraphSageRegressor(nn.Module):
            def __init__(self, input_size: int, hidden_size: int) -> None:
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(input_size * 2, hidden_size),
                    nn.ReLU(),
                    nn.Dropout(0.1),
                    nn.Linear(hidden_size, hidden_size),
                    nn.ReLU(),
                )
                self.head = nn.Sequential(
                    nn.Linear(hidden_size, hidden_size // 2),
                    nn.ReLU(),
                    nn.Linear(hidden_size // 2, 1),
                    nn.Sigmoid(),
                )

            def forward(self, self_features: Any, neighbor_features: Any) -> Any:
                merged = torch.cat([self_features, neighbor_features], dim=-1)
                return self.head(self.encoder(merged)).squeeze(-1)

        self.torch = torch
        payload = _load_checkpoint_safely(torch, path, required_keys={"scaler", "model_state"})
        self.scaler = payload["scaler"]
        self.target_name = str(payload.get("target_name", "rt"))
        self.feature_names = list(payload.get("feature_names", []))
        self.model = GraphSageRegressor(
            input_size=int(payload.get("input_size", 12)),
            hidden_size=int(payload.get("hidden_size", 64)),
        )
        self.model.load_state_dict(payload["model_state"])
        self.model.eval()

    def predict(self, self_features: list[float], neighbor_features: list[float]) -> float:
        torch = self.torch
        mean_values = self.scaler["mean"]
        std_values = self.scaler["std"]

        def normalize(values: list[float]) -> list[float]:
            return [
                (value - mean_values[index]) / (std_values[index] or 1.0)
                for index, value in enumerate(values)
            ]

        with torch.no_grad():
            self_tensor = torch.tensor([normalize(self_features)], dtype=torch.float32)
            neighbor_tensor = torch.tensor([normalize(neighbor_features)], dtype=torch.float32)
            pred = float(self.model(self_tensor, neighbor_tensor).item())
        if self.target_name == "path_stability_score":
            return clamp(pred)
        try:
            return max(1.0, math.expm1(pred))
        except OverflowError:
            return 1e9

    def feature_shift_diagnostics(
        self,
        self_features: list[float],
        neighbor_features: list[float],
    ) -> dict[str, Any]:
        """Flag model inputs far outside the training feature distribution."""
        mean_values = self.scaler["mean"]
        std_values = self.scaler["std"]
        names = self.feature_names or [f"feature_{index}" for index in range(len(self_features))]
        shifted: list[tuple[str, float]] = []
        for prefix, values in (("self", self_features), ("neighbor", neighbor_features)):
            for index, value in enumerate(values):
                std = float(std_values[index] or 1.0)
                z_score = abs((float(value) - float(mean_values[index])) / std)
                shifted.append((f"{prefix}.{names[index]}", z_score))
        shifted.sort(key=lambda item: item[1], reverse=True)
        extreme = [
            {"feature": feature, "abs_z": round(abs_z, 2)}
            for feature, abs_z in shifted
            if abs_z > GNN_MAX_FEATURE_Z
        ]
        return {
            "applicable": not extreme,
            "max_abs_z": round(shifted[0][1], 2) if shifted else 0.0,
            "threshold_abs_z": GNN_MAX_FEATURE_Z,
            "extreme_features": extreme[:8],
        }


class TrainedModelRuntime:
    def __init__(self, model_dir: str | Path | None = None, *, fail_fast: bool = False) -> None:
        self.model_dir = resolve_model_dir(model_dir)
        self.fail_fast = fail_fast
        self.lstm: LstmLatencyModel | None = None
        self.gnn: GraphSageStabilityModel | None = None
        self.status = "not_loaded"
        self.detail = ""
        self.load_error: str | None = None
        self.loaded_models: list[str] = []
        self.missing_models: list[str] = []
        self._load()

    def _load(self) -> None:
        self.lstm = None
        self.gnn = None
        self.loaded_models = []
        self.missing_models = []
        self.load_error = None
        load_errors: dict[str, str] = {}

        model_specs = {
            "lstm": (LstmLatencyModel, self.model_dir / MODEL_FILES["lstm"]),
            "gnn": (GraphSageStabilityModel, self.model_dir / MODEL_FILES["gnn"]),
        }
        for name, (loader, model_path) in model_specs.items():
            if not model_path.exists():
                self.missing_models.append(name)
                continue
            try:
                setattr(self, name, loader(model_path))
                self.loaded_models.append(name)
            except Exception as exc:  # noqa: BLE001
                load_errors[name] = str(exc)
                self.missing_models.append(name)

        if load_errors:
            self.load_error = "; ".join(f"{name}: {message}" for name, message in load_errors.items())
        if self.loaded_models:
            self.status = "loaded" if not load_errors else "partial"
            self.detail = ", ".join(self.loaded_models)
            if load_errors:
                self.detail += f"; failed: {', '.join(sorted(load_errors))}"
        elif load_errors:
            self.status = "fallback"
            self.detail = f"trained model load failed: {self.load_error}"
        else:
            self.status = "missing"
            self.detail = "model files were not found"

        if self.fail_fast and not self.loaded_models:
            if load_errors:
                raise RuntimeError(self.detail)
            expected = ", ".join(str(self.model_dir / filename) for filename in MODEL_FILES.values())
            raise FileNotFoundError(f"No trained model files were found. Expected one of: {expected}")

    def describe(self) -> dict[str, Any]:
        """Return an explicit model-runtime health payload for reports and tests."""
        trained_models = {
            name: str(self.model_dir / filename)
            for name, filename in MODEL_FILES.items()
        }
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "status": self.status,
            "detail": self.detail,
            "model_dir": str(self.model_dir),
            "loaded_models": list(self.loaded_models),
            "missing_models": list(self.missing_models),
            "trained_models": trained_models,
            "load_error": self.load_error,
        }
        if self.gnn is not None:
            payload["gnn"] = {
                "target_name": self.gnn.target_name,
                "feature_count": len(self.gnn.feature_names),
                "feature_names": list(self.gnn.feature_names),
            }
        if self.lstm is not None:
            payload["lstm"] = {
                "window": self.lstm.window,
                "input_size": int(getattr(self.lstm.model.lstm, "input_size", 2)),
            }
        return payload

    @property
    def enabled(self) -> bool:
        return self.lstm is not None or self.gnn is not None

    def predict(
        self,
        *,
        task: Task,
        node: Node,
        profile: NetworkPathProfile,
        latency_history_ms: list[float],
        node_load: float,
        bandwidth_utilization: float,
    ) -> ModelPrediction:
        if not self.enabled:
            return ModelPrediction(enabled=False, status=self.status, detail=self.detail)

        pressure_history = self._pressure_history(task, node_load, bandwidth_utilization, profile)
        lstm_latency = None
        if self.lstm is not None:
            available = node.available()
            cpu_util = clamp(1.0 - (available.cpu / max(node.capacity.cpu, 1e-6)))
            memory_util = clamp(1.0 - (available.memory / max(node.capacity.memory, 1e-6)))
            lstm_latency = self.lstm.predict(
                latency_history_ms,
                pressure_history,
                [cpu_util] * max(1, self.lstm.window),
                [memory_util] * max(1, self.lstm.window),
            )

        gnn_latency = None
        gnn_score = None
        gnn_raw_output = None
        gnn_applicable = None
        gnn_diagnostic = None
        gnn_feature_shift = None
        if self.gnn is not None:
            features = self._graph_features(node, task, profile, latency_history_ms, pressure_history)
            neighbor_features = self._neighbor_features(features)
            target = task.max_latency_ms or max(35.0, mean(latency_history_ms) * 1.5)
            raw_gnn = self.gnn.predict(features, neighbor_features)
            gnn_raw_output = raw_gnn
            gnn_feature_shift = self.gnn.feature_shift_diagnostics(features, neighbor_features)
            gnn_applicable = bool(gnn_feature_shift["applicable"])
            if not gnn_applicable:
                gnn_diagnostic = (
                    "GNN output excluded from scheduling: runtime features are outside "
                    f"the training distribution (max |z|={gnn_feature_shift['max_abs_z']})."
                )
            elif self.gnn.target_name == "path_stability_score":
                gnn_score = clamp(raw_gnn)
                gnn_latency = max(1.0, profile.robust_latency_ms() * (1.25 - (0.5 * gnn_score)))
            else:
                # Older trace models predicted RT. Bound transferred predictions so
                # domain-shift outliers do not dominate live scheduling.
                gnn_latency = min(raw_gnn, max(50.0, target * 4.0))
                gnn_score = clamp(1.0 / (1.0 + (gnn_latency / max(10.0, target))))

        return ModelPrediction(
            enabled=True,
            lstm_latency_ms=lstm_latency,
            gnn_latency_ms=gnn_latency,
            gnn_stability_score=gnn_score,
            gnn_raw_output=gnn_raw_output,
            gnn_applicable=gnn_applicable,
            gnn_diagnostic=gnn_diagnostic,
            gnn_feature_shift=gnn_feature_shift,
            status=self.status,
            detail=self.detail,
        )

    def _pressure_history(
        self,
        task: Task,
        node_load: float,
        bandwidth_utilization: float,
        profile: NetworkPathProfile,
    ) -> list[float]:
        base = max(0.0, task.network_sensitivity + node_load + bandwidth_utilization)
        loss = clamp(profile.packet_loss / 0.05)
        return [
            max(0.0, base * 0.75),
            max(0.0, base * 0.92),
            max(0.0, base + (loss * 0.15)),
            max(0.0, base * 1.08),
            max(0.0, base * 1.15 + (loss * 0.20)),
        ]

    def _graph_features(
        self,
        node: Node,
        task: Task,
        profile: NetworkPathProfile,
        latency_history_ms: list[float],
        pressure_history: list[float],
    ) -> list[float]:
        rt_values = [math.log1p(max(0.0, value)) for value in latency_history_ms]
        mcr_values = [math.log1p(max(0.0, value)) for value in pressure_history]
        in_degree = float(len(node.network_paths))
        out_degree = float(len(node.labels) + (1 if task.data_region else 0))
        total_degree = max(0.0, in_degree + out_degree)
        return [
            rt_values[-1],
            mean(rt_values),
            pstdev(rt_values) if len(rt_values) > 1 else 0.0,
            rt_values[-1] - rt_values[0],
            mcr_values[-1],
            mean(mcr_values),
            pstdev(mcr_values) if len(mcr_values) > 1 else 0.0,
            mcr_values[-1] - mcr_values[0],
            clamp(node_load_from_capacity(node)),
            clamp(node_load_from_capacity(node)),
            clamp(memory_util_from_capacity(node)),
            clamp(memory_util_from_capacity(node)),
            math.log1p(in_degree),
            math.log1p(out_degree),
            math.log1p(total_degree),
            math.log1p(max(0.0, profile.robust_latency_ms())),
        ]

    def _neighbor_features(self, features: list[float]) -> list[float]:
        # Runtime topology telemetry is not available yet; use the candidate path embedding
        # as a conservative self-neighbor until live service-call neighbors are connected.
        return list(features)


_DEFAULT_RUNTIME: TrainedModelRuntime | None = None


def get_default_model_runtime(
    model_dir: str | Path | None = None,
    *,
    fail_fast: bool = False,
    reset: bool = False,
) -> TrainedModelRuntime:
    global _DEFAULT_RUNTIME
    if model_dir is not None or reset:
        return TrainedModelRuntime(model_dir=model_dir, fail_fast=fail_fast)
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = TrainedModelRuntime(fail_fast=fail_fast)
    return _DEFAULT_RUNTIME


def node_load_from_capacity(node: Node) -> float:
    available = node.available()
    cpu = 1.0 - (available.cpu / max(node.capacity.cpu, 1e-6))
    memory = 1.0 - (available.memory / max(node.capacity.memory, 1e-6))
    return (clamp(cpu) + clamp(memory)) / 2.0


def memory_util_from_capacity(node: Node) -> float:
    available = node.available()
    return 1.0 - (available.memory / max(node.capacity.memory, 1e-6))
