from __future__ import annotations

import json
from argparse import Namespace

from tianjun.config import TianjunConfig, first_present
from tianjun.config.secrets import delete_secret, describe_secret, secret_path_from_config, write_secret
from tianjun.cli import resolved_llm_settings


def handle(args: Namespace, app_config: TianjunConfig) -> None:
    secret_path = secret_path_from_config(app_config.get("llm.secrets_file"))
    secret_key = str(first_present(app_config.get("llm.api_key_secret"), default="llm.api_key"))
    if args.secrets_command == "set":
        written = write_secret(args.api_key, secret_path, key=secret_key)
        print(json.dumps({
            "status": "ok",
            "provider": args.provider,
            "path": str(written),
            "key": secret_key,
            "message": "API key stored in the user-level secrets file. The raw key was not printed.",
        }, ensure_ascii=False, indent=2))
        return
    if args.secrets_command == "show":
        settings = resolved_llm_settings(args, app_config)
        description = describe_secret(secret_path, key=secret_key)
        print(json.dumps({
            "provider": args.provider,
            "configured_secret": description,
            "effective_llm_key_source": settings.api_key_source,
            "effective_llm_key_present": bool(settings.api_key),
            "effective_llm_key_fingerprint": settings.key_fingerprint(),
        }, ensure_ascii=False, indent=2))
        return
    if args.secrets_command == "path":
        print(str(secret_path))
        return
    if args.secrets_command == "remove":
        removed = delete_secret(secret_path, key=secret_key)
        print(json.dumps({"status": "removed" if removed else "not_found", "path": str(secret_path), "key": secret_key}, ensure_ascii=False, indent=2))
        return
    raise ValueError(f"Unsupported secrets command: {args.secrets_command}")
