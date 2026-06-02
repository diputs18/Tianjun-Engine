# Hermes Policy Flow Optimization

## Overview

This update improves Hermes from a mostly single-label requirement parser into a
multi-objective policy generator with a clearer feedback loop. Natural-language
requirements now carry more scheduling intent into the resource scoring stage,
while clarification questions focus on information that materially affects the
result.

## Implemented Optimizations

### 1. Implicit Workload Recognition

Hermes now recognizes workload types from common business descriptions, even
when the user does not explicitly name a technical workload category.

Examples include:

- Online Q&A and dialogue services as inference workloads.
- Embedding and vectorization tasks as inference workloads.
- Batch tagging, annotation, data cleaning, and ETL as batch workloads.

### 2. Region Parsing and Typo Recovery

Region parsing now covers additional cities and common abbreviations, including
`cd` and `cq`. City names are mapped to service regions consistently across the
policy and node layers.

Hermes also supports context-constrained fuzzy recovery for minor region typos.
For example, a typo such as `成嘟` can still resolve to the west region without
turning arbitrary text into a region match.

### 3. Multi-Objective Priority Vector

The original enum-style priority is retained for compatibility, but Hermes now
also records a continuous `priority_vector`.

Supported dimensions:

- `latency`
- `cost`
- `quality`
- `security`
- `balance`
- `fragmentation`
- `locality`
- `network`

The vector is translated into scheduler metric weights and passed into each
task through `intent_weights`. This allows mixed requirements such as
low-latency, network-sensitive, and security-aware workloads to affect actual
resource ranking.

### 4. Workload-Aware Confidence

Hermes now tracks confidence per requirement slot instead of relying on a fixed
incremental score. The aggregate confidence is weighted by workload type:

- Inference and streaming workloads emphasize latency evidence.
- Training workloads emphasize resource evidence.
- Region, budget, security, and priority evidence retain independent scores.

### 5. Feedback-to-Scheduler Alignment

Feedback deltas now use the scheduler's real metric keys instead of detached
alias weights. Hermes can directly adjust preferences for:

- Performance and completion
- Cost
- Reliability and security
- Balance and fragmentation
- Locality and network quality

Legacy aliases remain mapped for compatibility.

### 6. Feedback Intensity

Adjustment strength now reflects natural-language intensity. Expressions such
as slightly, somewhat, very, and extreme no longer produce identical changes.

### 7. Impact-Ranked Clarification

Clarification questions are ordered by expected scheduling impact. Hermes also
checks online inventory before asking follow-up questions and explicitly reports
when the requested service region currently has no online nodes.

## Main Code Areas

| Area | Files | Purpose |
| --- | --- | --- |
| Requirement model | `src/tianjun/core/policy.py` | Adds priority vectors, metric preferences, and slot confidence. |
| Requirement parsing | `src/tianjun/policy/generator.py` | Adds intent recognition, region recovery, confidence calculation, and scheduler weight generation. |
| Feedback loop | `src/tianjun/policy/feedback.py` | Aligns feedback with scheduler metrics and adds intensity handling. |
| Clarification | `src/tianjun/policy/clarifier.py` | Ranks questions by impact and checks available regions. |
| Scheduling | `src/tianjun/domain/task.py`, `src/tianjun/scheduling/engine.py` | Carries and applies semantic intent weights. |
| Runtime integration | `src/tianjun/application/control_plane.py`, `src/tianjun/chat/runtime.py` | Connects inventory-aware questions and validates vector output. |
| Region mapping | `src/tianjun/domain/node.py` | Expands city-to-service-region mappings. |

## Validation

The update includes `tests/test_hermes_optimization.py`, covering:

- Implicit workload inference.
- Region aliases and typo-tolerant matching.
- Multi-objective vector propagation into scheduler metrics.
- Workload-aware slot confidence.
- Feedback metric alignment and intensity.
- Balance preference propagation.
- Inventory-aware clarification for unavailable regions.

Validation commands:

```powershell
python -m pytest
python -m compileall -q src tests
git diff --check
```

Expected result:

```text
10 passed
```
