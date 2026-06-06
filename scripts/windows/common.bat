@echo off
set "TJ_HOST=127.0.0.1"
set "TJ_PORT=8024"
set "TJ_CONFIG=configs\tianjun.example.toml"
set "TJ_SIM_INVENTORY=configs\sim_cluster.example.json"
set "TJ_URL=http://%TJ_HOST%:%TJ_PORT%/dashboard"
set "TJ_BASE_URL=http://%TJ_HOST%:%TJ_PORT%"
set "TJ_START_MCP=1"
set "TJ_OPEN_DASHBOARD=1"
exit /b 0
