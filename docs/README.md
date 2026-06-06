# Tianjun 文档索引

当您需要快速找到合适的维护面时，请从这里开始。

| 主题 | 文档 |
| --- | --- |
| 系统形态、职责和控制平面边界 | [architecture.md](architecture.md) |
| 官方 HTTP API 和遗留路由归属 | [api.md](api.md) |
| 已弃用的端点和迁移路径 | [deprecation.md](deprecation.md) |
| 确认、执行器、密钥和生产安全边界 | [security-boundary.md](security-boundary.md) |
| DCI 参考数据、模型资产和复现说明 | [experiments-dci.md](experiments-dci.md) |
| 手动 Dashboard 验收检查 | [dashboard-test-checklist.md](dashboard-test-checklist.md) |
| Final convergence freeze checks | [convergence-checklist.md](convergence-checklist.md) |

用于日常验证的运行：

```powershell
python -m pytest
python scripts\smoke_test.py
```
