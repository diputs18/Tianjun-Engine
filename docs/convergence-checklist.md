# Architecture Convergence Checklist

Use this checklist before declaring the current research-engineering convergence phase complete.

## Required Commands

```powershell
python -m py_compile `
  src\tianjun\cli\__init__.py `
  src\tianjun\application\control_plane.py `
  src\tianjun\application\node_registry.py `
  src\tianjun\application\task_lease_service.py `
  src\tianjun\application\requirement_dialogue.py `
  src\tianjun\application\policy_workflow.py `
  src\tianjun\interfaces\http\server.py `
  src\tianjun\interfaces\http\legacy_routes.py `
  scripts\smoke_test.py `
  scripts\convergence_check.py

python -m pytest
python scripts\smoke_test.py --port 8135
python scripts\convergence_check.py
```

## Runtime Checks

- Offline server starts with `python -B main.py serve --config configs\tianjun.example.toml --offline`.
- `/health` returns `status=ok`.
- `/report` returns control-plane state.
- `/dashboard` serves the static Dashboard.
- Official chat route `/chat/sessions` starts a session.
- Legacy `/intent` defaults to preview.
- Legacy `/intent` with `dry_run=false` and no confirmation returns 403.
- Node registration and heartbeat work through `NodeRegistry`.
- Task submit, preview, schedule, and lease issue work through `TaskLeaseService`.
- Requirement parse and session continue work through `RequirementDialogueService`.
- Policy draft, compare, simulate, commit, and feedback optimize work through `PolicyWorkflowService`.
- MCP contract imports and matches registered tools.

## Static Checks

- `CentralControlPlane` is facade + shared state + report/restore/topology/execution cross-cutting.
- `node_registry.py` owns node lifecycle.
- `task_lease_service.py` owns task and lease lifecycle.
- `requirement_dialogue.py` owns requirement dialogue lifecycle.
- `policy_workflow.py` owns policy lifecycle.
- `cli/__init__.py` contains parser/config/dispatch only; command bodies live in `cli/commands/`.
- Deprecated routes are implemented only in `interfaces/http/legacy_routes.py`.
- Dashboard static JavaScript does not call `/intent`, `/chat`, or `/hermes/*`.
- `requirements.txt` is explanatory and does not duplicate dependency facts from `pyproject.toml`.
- README and docs describe the same service boundaries and confirmation rules.

## Future Work

These are intentionally outside the current convergence phase:

- Production authentication, RBAC, TLS, multi-tenant authorization.
- Full decoupling of services from the `CentralControlPlane` state object.
- Dashboard UI redesign.
- Model/data asset relocation.
- Scheduler algorithm changes.
