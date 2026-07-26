"""Domain objects for Tianjun scheduling.

This package intentionally exports the stable domain API from focused modules.
Import implementation files directly when a narrower dependency is preferred.
"""

from .common import (
    GROUP_INNER_WEIGHTS,
    GROUP_KEYS,
    METRIC_KEYS,
    METRIC_TO_GROUP,
    OBJECTIVE_GROUPS,
    RESOURCE_FIELDS,
    clamp,
    normalize_weights,
    round_payload,
)
from .batch import (
    BatchAssignment,
    BatchSchedulingPlan,
    BatchStatus,
    BatchValidationIssue,
    BatchValidationReport,
    ReservationLedger,
    ResourceSnapshot,
    TaskBatch,
    UnassignedTask,
)
from .carbon import CarbonSiteProfile, PowerProfile, operational_carbon
from .decision import SchedulingDecision
from .execution import ExecutionMode, ExecutionRecord, TaskExecutionSpec
from .network import NetworkPathProfile, PhysicalTopology, TopologyEdge
from .node import Node
from .policy import PolicyAdjustment, PolicyState
from .resource import ResourceVector
from .task import RunningTask, Task, TaskStatus

__all__ = [
    "METRIC_KEYS",
    "GROUP_KEYS",
    "GROUP_INNER_WEIGHTS",
    "METRIC_TO_GROUP",
    "OBJECTIVE_GROUPS",
    "RESOURCE_FIELDS",
    "BatchAssignment",
    "BatchSchedulingPlan",
    "BatchStatus",
    "BatchValidationIssue",
    "BatchValidationReport",
    "CarbonSiteProfile",
    "ExecutionMode",
    "ExecutionRecord",
    "NetworkPathProfile",
    "PhysicalTopology",
    "Node",
    "PolicyAdjustment",
    "PolicyState",
    "PowerProfile",
    "ReservationLedger",
    "ResourceSnapshot",
    "ResourceVector",
    "RunningTask",
    "SchedulingDecision",
    "Task",
    "TaskExecutionSpec",
    "TaskStatus",
    "TaskBatch",
    "TopologyEdge",
    "UnassignedTask",
    "clamp",
    "normalize_weights",
    "operational_carbon",
    "round_payload",
]
