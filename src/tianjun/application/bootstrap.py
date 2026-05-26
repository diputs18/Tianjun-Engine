from __future__ import annotations

from pathlib import Path

from ..domain import PolicyState
from ..ml.runtime import TrainedModelRuntime
from ..scheduling.engine import ClosedLoopAdaptiveScheduler
from ..storage.sqlite_state_store import SQLiteStateStore
from .control_plane import CentralControlPlane


def build_control_plane(
    *,
    policy_state: PolicyState | None = None,
    policy_update_interval: int = 2,
    heartbeat_timeout_seconds: float = 15.0,
    state_store: SQLiteStateStore | None = None,
    model_dir: str | Path | None = None,
    require_model: bool = False,
) -> CentralControlPlane:
    """Build a control plane with explicit model-runtime wiring.

    Keeping this wiring in one place prevents command-line entrypoints, tests,
    and future services from each constructing their own implicit scheduler or
    model singleton.
    """
    policy = policy_state or PolicyState()
    model_runtime = TrainedModelRuntime(model_dir=model_dir, fail_fast=require_model)
    scheduler = ClosedLoopAdaptiveScheduler(policy, model_runtime=model_runtime)
    return CentralControlPlane(
        policy_state=policy,
        policy_update_interval=policy_update_interval,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        state_store=state_store,
        scheduler=scheduler,
    )
