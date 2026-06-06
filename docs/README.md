# Tianjun Documentation Index

Start here when you need to find the right maintenance surface quickly.

| Topic | Document |
| --- | --- |
| System shape, responsibilities, and control-plane boundaries | [architecture.md](architecture.md) |
| Official HTTP API and legacy route ownership | [api.md](api.md) |
| Deprecated endpoints and migration path | [deprecation.md](deprecation.md) |
| Confirmation, executor, secret, and production safety boundaries | [security-boundary.md](security-boundary.md) |
| DCI reference data, model assets, and reproduction notes | [experiments-dci.md](experiments-dci.md) |
| Manual Dashboard acceptance checks | [dashboard-test-checklist.md](dashboard-test-checklist.md) |

For day-to-day verification, run:

```powershell
python -m pytest
python scripts\smoke_test.py
```
