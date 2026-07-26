from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .control_plane import CentralControlPlane


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LifecycleSweeper:
    """Expire stale nodes and leases independently from user traffic."""

    control_plane: CentralControlPlane
    interval_seconds: float = 1.0
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    run_count: int = field(default=0, init=False)
    failure_count: int = field(default=0, init=False)
    last_run_epoch: float | None = field(default=None, init=False)
    last_error: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("lifecycle sweep interval must be positive")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="tianjun-lifecycle-sweeper",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        if thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if thread.is_alive():
            raise RuntimeError("lifecycle sweeper did not stop before timeout")
        self._thread = None

    def sweep_once(self) -> None:
        try:
            with self.control_plane.lock:
                self.control_plane._expire_stale_nodes()
            self.run_count += 1
            self.last_run_epoch = time.time()
            self.last_error = None
        except Exception as exc:  # keep maintenance alive; surface state via snapshot
            self.failure_count += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.exception("Lifecycle sweep failed")

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "last_run_epoch": self.last_run_epoch,
            "last_error": self.last_error,
        }

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self.sweep_once()
