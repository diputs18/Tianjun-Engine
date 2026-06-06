# Deprecation Plan

Tianjun keeps compatibility routes available while steering all new clients to the official session-based chat API.

## Deprecated Routes

| Deprecated route | Replacement | Notes |
| --- | --- | --- |
| `POST /intent` | `POST /chat/sessions` followed by explicit commit | Legacy one-shot gateway; kept for older dashboards and demos |
| `POST /chat` | `POST /chat/sessions` | Old non-session-styled chat entry |
| `POST /hermes/chat` | `POST /chat/sessions` | Old Hermes wrapper response shape |
| `POST /hermes/chat/stream` | `POST /chat/sessions/stream` | Old SSE event shape |
| `GET /hermes/status` | `GET /health` | Status compatibility alias |

## Migration Rules

- New Dashboard code must call `/chat/sessions*` only.
- MCP tools must use official HTTP routes.
- Legacy routes must remain in the legacy adapter and must be tested.
- Removal can happen only after downstream scripts and demos no longer call the deprecated paths.
