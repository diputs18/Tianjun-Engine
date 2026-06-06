# Security Boundary

Tianjun is a local research and demo control plane. Production use requires additional authentication, authorization, isolation, auditing, and executor hardening.

## Confirmation Boundary

The following operations require an explicit confirmation parameter or Dashboard button flow:

- `POST /policies/commit`
- `POST /tasks/{task_id}/schedule`
- `POST /policy-weights`
- MCP `commit_policy(..., confirmed=true)`
- MCP `schedule_pending_task(..., confirmed=true)`

Natural-language messages such as "confirm" are not enough to bypass the API confirmation boundary.

## Executor Boundary

The default configuration keeps process, Docker, and Kubernetes executors disabled. Enable them only with clear host-level isolation, command allowlists, resource limits, and audit logging.

## Secret Boundary

Do not write real API keys to repository files. Prefer:

```powershell
python -B main.py secrets --config configs\tianjun.example.toml set deepseek --api-key "..."
```

Environment variables and ignored local `.env` files are supported for CI or container setups.

## LLM Boundary

The LLM may explain, summarize, and help parse user requirements. It must not invent inventory, commit tasks, mutate policy state, or create leases except through explicit tool/API calls.
