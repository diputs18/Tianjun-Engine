"""Domain objects for Tianjun scheduling.

This package intentionally exports the stable domain API from focused modules.
Import implementation files directly when a narrower dependency is preferred.
"""

from .common import METRIC_KEYS, RESOURCE_FIELDS, clamp, normalize_weights, round_payload
from .decision import SchedulingDecision
from .execution import ExecutionMode, ExecutionRecord, TaskExecutionSpec
from .network import NetworkPathProfile, PhysicalTopology, TopologyEdge
from .node import Node
from .policy import PolicyAdjustment, PolicyState
from .resource import ResourceVector
from .task import RunningTask, Task, TaskStatus

__all__ = [
    "METRIC_KEYS",
    "RESOURCE_FIELDS",
    "ExecutionMode",
    "ExecutionRecord",
    "NetworkPathProfile",
    "PhysicalTopology",
    "Node",
    "PolicyAdjustment",
    "PolicyState",
    "ResourceVector",
    "RunningTask",
    "SchedulingDecision",
    "Task",
    "TaskExecutionSpec",
    "TaskStatus",
    "TopologyEdge",
    "clamp",
    "normalize_weights",
    "round_payload",
]
