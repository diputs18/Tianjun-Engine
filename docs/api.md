# HTTP API

The official API is JSON over the standard-library HTTP server. Request and response bodies are UTF-8 JSON unless the route is an SSE stream or Dashboard HTML/static content.

## Official Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Runtime health, model status, chat runtime status |
| GET | `/report` | Control-plane state for Dashboard and tools |
| GET | `/dashboard` | Static Dashboard shell |
| GET | `/chat/sessions/{session_id}` | Read chat session state |
| POST | `/chat/sessions` | Start a chat session |
| POST | `/chat/sessions/stream` | Start or continue chat through SSE |
| POST | `/chat/sessions/{session_id}/messages` | Continue a chat session |
| POST | `/chat/sessions/{session_id}/messages/stream` | Continue a chat session through SSE |
| POST | `/chat/sessions/{session_id}/commit` | Commit the selected chat policy |
| POST | `/requirements/parse` | Parse a single requirement |
| GET | `/conversations/{session_id}` | Read structured requirement dialogue |
| POST | `/conversations/start` | Start structured requirement dialogue |
| POST | `/conversations/{session_id}/continue` | Continue structured requirement dialogue |
| POST | `/conversations/{session_id}/draft` | Draft a policy from a requirement dialogue |
| GET | `/policies/{policy_id}` | Explain/read a policy |
| POST | `/policies/draft` | Draft a policy |
| POST | `/policies/compare` | Compare policy options |
| POST | `/policies/simulate` | Simulate a policy |
| POST | `/policies/commit` | Commit a policy; requires explicit confirmation |
| POST | `/policies/{policy_id}/optimize` | Optimize a policy from feedback |
| POST | `/policies/{policy_id}/resimulate` | Re-run policy simulation |
| POST | `/policy-weights` | Update scheduler weights; requires explicit confirmation |
| POST | `/feedback/parse` | Parse user feedback |
| POST | `/feedback` | Record user feedback |
| POST | `/topology/register` | Register physical topology |
| POST | `/nodes/register` | Register node inventory |
| POST | `/nodes/heartbeat` | Update node heartbeat and telemetry |
| POST | `/tasks` | Submit a task |
| POST | `/tasks/{task_id}/schedule` | Schedule a pending task; requires explicit confirmation |
| POST | `/leases/next` | Node agent lease polling |
| POST | `/task-runs/progress` | Report task progress |
| POST | `/task-runs/result` | Report final task result |
| POST | `/task-runs/cancel` | Cancel an active task run |
| POST | `/schedule/preview` | CloudSimPlus-compatible schedule preview |
| POST | `/schedule/commit` | CloudSimPlus-compatible direct commit |

## Legacy Routes

These routes remain available for compatibility but are deprecated:

| Method | Path | Replacement |
| --- | --- | --- |
| POST | `/intent` | `/chat/sessions` or `/chat/sessions/stream` |
| POST | `/chat` | `/chat/sessions` |
| POST | `/hermes/chat` | `/chat/sessions` |
| POST | `/hermes/chat/stream` | `/chat/sessions/stream` |
| GET | `/hermes/status` | `/health` |

New clients should use official routes. Legacy routes are centralized in the HTTP legacy adapter and covered by route regression tests.
