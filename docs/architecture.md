# Architecture

Tianjun Engine is organized around a small set of public adapters and a central application facade.

## Runtime Flow

1. A user talks to the Dashboard, CLI chat, or an MCP host.
2. `ChatRuntime` separates general chat from scheduling requirements.
3. Requirement and policy tools call `CentralControlPlane`.
4. The control plane coordinates policy generation, deterministic scheduling, task lease creation, and execution feedback.
5. Simulated nodes, CloudSimPlus bridges, or real node agents register inventory and report progress/results.
6. Reports and health data are exposed through HTTP and rendered by the Dashboard.

## Main Subsystems

| Subsystem | Responsibility |
| --- | --- |
| HTTP interface | Official REST/SSE API, Dashboard static serving, legacy compatibility adapter |
| Dashboard | Static HTML/CSS/JS control surface using official APIs |
| Chat runtime | Hermes-style dialogue, policy option selection, explicit commit flow |
| Control-plane facade | Stable API used by HTTP, chat, MCP, and tests |
| Scheduling engine | Deterministic node filtering and multi-objective scoring |
| Policy workflow | Requirement parsing, policy drafting, simulation, feedback optimization |
| Node/lease flow | Node registration, heartbeat, task lifecycle, lease/result reporting |
| MCP adapter | Tool exposure for MCP hosts through HTTP wrappers |

## Control-Plane Responsibility Map

| Area | Current facade methods |
| --- | --- |
| Nodes and topology | `register_node`, `record_heartbeat`, `register_topology`, `_node_report_payload`, stale node recovery |
| Tasks and leases | `submit_task`, `preview_task`, `schedule_pending_task`, `request_lease`, progress/result/cancel reporting |
| Requirements | `parse_requirement`, requirement session start/continue/read helpers |
| Policy workflow | draft, compare, simulate, explain/get, commit, weight updates |
| Feedback | parse, record, optimize from feedback |
| Reporting | `build_report`, `current_tick`, active run payloads, SLA summaries |
| Persistence | SQLite restore and per-entity persist helpers |

The long-term direction is to keep `CentralControlPlane` as a facade while extracting services for node registry, task lease lifecycle, policy workflow, and requirement dialogue. The facade API remains stable for HTTP, ChatRuntime, MCP, and existing tests.
