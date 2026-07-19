from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from .common import RESOURCE_FIELDS, clamp


@dataclass(slots=True)
class ResourceVector:
    """Shared capacity contract.

    CPU/RAM/GPU/storage preserve the original public API.  The additional
    fields make CloudSim's PE throughput and I/O resources explicit while
    remaining backwards compatible because unspecified dimensions default to
    zero and are ignored when a node does not model them.
    """

    cpu: float = 0.0
    memory: float = 0.0
    gpu: float = 0.0
    storage: float = 0.0
    mips: float = 0.0
    gpu_memory: float = 0.0
    storage_iops: float = 0.0
    bandwidth: float = 0.0

    def fits_in(self, other: "ResourceVector") -> bool:
        return all(getattr(self, field) <= getattr(other, field) + 1e-9 for field in RESOURCE_FIELDS)

    def clamp_non_negative(self) -> "ResourceVector":
        return ResourceVector(
            cpu=max(0.0, self.cpu),
            memory=max(0.0, self.memory),
            gpu=max(0.0, self.gpu),
            storage=max(0.0, self.storage),
            mips=max(0.0, self.mips),
            gpu_memory=max(0.0, self.gpu_memory),
            storage_iops=max(0.0, self.storage_iops),
            bandwidth=max(0.0, self.bandwidth),
        )

    def ratios_against(self, total: "ResourceVector") -> dict[str, float]:
        ratios: dict[str, float] = {}
        for field in RESOURCE_FIELDS:
            capacity = getattr(total, field)
            ratios[field] = 0.0 if capacity <= 0 else getattr(self, field) / capacity
        return ratios

    def active_ratios_against(self, total: "ResourceVector") -> list[float]:
        ratios = self.ratios_against(total)
        return [ratios[field] for field in RESOURCE_FIELDS if getattr(total, field) > 0]

    def dominant_share_against(self, total: "ResourceVector") -> float:
        ratios = self.active_ratios_against(total)
        return max(ratios, default=0.0)

    def fragmentation_score_against(self, total: "ResourceVector") -> float:
        ratios = self.active_ratios_against(total)
        if len(ratios) <= 1:
            return 1.0
        return clamp(1.0 - (pstdev(ratios) * 1.8))

    def to_dict(self) -> dict[str, float]:
        return {field: getattr(self, field) for field in RESOURCE_FIELDS}

    def __add__(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            cpu=self.cpu + other.cpu,
            memory=self.memory + other.memory,
            gpu=self.gpu + other.gpu,
            storage=self.storage + other.storage,
            mips=self.mips + other.mips,
            gpu_memory=self.gpu_memory + other.gpu_memory,
            storage_iops=self.storage_iops + other.storage_iops,
            bandwidth=self.bandwidth + other.bandwidth,
        )

    def __sub__(self, other: "ResourceVector") -> "ResourceVector":
        return ResourceVector(
            cpu=self.cpu - other.cpu,
            memory=self.memory - other.memory,
            gpu=self.gpu - other.gpu,
            storage=self.storage - other.storage,
            mips=self.mips - other.mips,
            gpu_memory=self.gpu_memory - other.gpu_memory,
            storage_iops=self.storage_iops - other.storage_iops,
            bandwidth=self.bandwidth - other.bandwidth,
        )
