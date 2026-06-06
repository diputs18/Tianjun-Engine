from __future__ import annotations

import json
from argparse import Namespace

from tianjun.cli import require_model, resolved_model_dir, resolved_path_setting
from tianjun.config import TianjunConfig, first_present
from tianjun.execution.runtime_demo import run_runtime_demo
from tianjun.observability.reporting import format_report


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    scenario = resolved_path_setting(
        args.scenario,
        app_config,
        "runtime_demo.scenario",
        "scenario.path",
        default="examples/runtime_scenario.json",
    )
    state_db = resolved_path_setting(args.state_db, app_config, "runtime_demo.state_db")
    max_rounds = int(first_present(args.max_rounds, app_config.get("runtime_demo.max_rounds"), default=40))
    payload = run_runtime_demo(
        scenario,
        max_rounds=max_rounds,
        state_db_path=state_db,
        model_dir=resolved_model_dir(args, app_config),
        require_model=require_model(args, app_config),
    )
    report = payload["report"]
    print(format_report(report))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
