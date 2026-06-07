from __future__ import annotations

import json
from argparse import Namespace

from tianjun.config import TianjunConfig
from tianjun.cli import resolved_llm_settings
from tianjun.llm import OpenAICompatibleClient


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    settings = resolved_llm_settings(args, app_config)
    print(json.dumps(settings.describe(), ensure_ascii=False, indent=2))
    settings.validate_for_chat()
    if not settings.enabled():
        print(json.dumps({"status": "skipped", "reason": "LLM is offline or disabled."}, ensure_ascii=False, indent=2))
        return
    if "api.deepseek.com" in str(settings.base_url) and not settings.api_key:
        raise ValueError("DeepSeek API requires an API key. Run `tianjun secrets set deepseek --api-key YOUR_KEY`, or set DEEPSEEK_API_KEY in .env / process environment.")
    client = OpenAICompatibleClient(settings)
    reply = client.chat([
        {"role": "system", "content": "You are a connection test assistant. Reply only with OK."},
        {"role": "user", "content": "Please reply OK."},
    ], timeout_seconds=min(10.0, settings.timeout_seconds))
    print(json.dumps({"status": "ok", "reply": reply}, ensure_ascii=False, indent=2))
