from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from .paths import resolve_path, user_config_dir


DEFAULT_SECRET_KEY = "llm.api_key"


def default_secrets_file() -> Path:
    """Return the cross-platform per-user Tianjun secrets file."""
    return user_config_dir() / "secrets.toml"


def secret_path_from_config(value: str | os.PathLike[str] | None) -> Path:
    path = resolve_path(value) if value else default_secrets_file()
    return path or default_secrets_file()


def read_toml(path: str | os.PathLike[str]) -> dict[str, Any]:
    secret_path = Path(path)
    if not secret_path.exists():
        return {}
    return tomllib.loads(secret_path.read_text(encoding="utf-8"))


def get_dotted(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_dotted(payload: dict[str, Any], dotted_path: str, value: Any) -> dict[str, Any]:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value
    return payload


def delete_dotted(payload: dict[str, Any], dotted_path: str) -> bool:
    current: Any = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    del current[parts[-1]]
    return True


def read_secret(path: str | os.PathLike[str] | None = None, *, key: str = DEFAULT_SECRET_KEY) -> tuple[str | None, str | None]:
    secret_path = Path(path) if path else default_secrets_file()
    payload = read_toml(secret_path)
    value = get_dotted(payload, key)
    if isinstance(value, str) and value.strip():
        return value.strip(), f"secrets:{secret_path}:{key}"
    return None, None


def write_secret(
    value: str,
    path: str | os.PathLike[str] | None = None,
    *,
    key: str = DEFAULT_SECRET_KEY,
) -> Path:
    secret_path = Path(path) if path else default_secrets_file()
    payload = read_toml(secret_path)
    set_dotted(payload, key, value.strip())
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(_toml_dump(payload), encoding="utf-8")
    _restrict_owner_read_write(secret_path)
    return secret_path


def delete_secret(path: str | os.PathLike[str] | None = None, *, key: str = DEFAULT_SECRET_KEY) -> bool:
    secret_path = Path(path) if path else default_secrets_file()
    payload = read_toml(secret_path)
    removed = delete_dotted(payload, key)
    if removed:
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(_toml_dump(payload), encoding="utf-8")
        _restrict_owner_read_write(secret_path)
    return removed


def describe_secret(path: str | os.PathLike[str] | None = None, *, key: str = DEFAULT_SECRET_KEY) -> dict[str, Any]:
    secret_path = Path(path) if path else default_secrets_file()
    value, source = read_secret(secret_path, key=key)
    return {
        "path": str(secret_path),
        "key": key,
        "present": bool(value),
        "source": source,
        "fingerprint": _fingerprint(value),
    }


def _fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _restrict_owner_read_write(path: Path) -> None:
    if os.name == "nt":
        # Windows ACLs are managed by the user profile. Avoid brittle chmod semantics.
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _toml_dump(payload: dict[str, Any]) -> str:
    """Small TOML writer for the nested string/bool/int/float values we use."""
    lines: list[str] = []
    scalar_items = {k: v for k, v in payload.items() if not isinstance(v, dict)}
    for key, value in scalar_items.items():
        lines.append(f"{key} = {_toml_value(value)}")
    dict_items = {k: v for k, v in payload.items() if isinstance(v, dict)}
    if scalar_items and dict_items:
        lines.append("")
    for idx, (section, values) in enumerate(dict_items.items()):
        if idx and lines and lines[-1] != "":
            lines.append("")
        _dump_section(lines, section, values)
    return "\n".join(lines).rstrip() + "\n"


def _dump_section(lines: list[str], section: str, values: dict[str, Any]) -> None:
    scalars: dict[str, Any] = {}
    nested: dict[str, dict[str, Any]] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            nested[key] = value
        else:
            scalars[key] = value
    lines.append(f"[{section}]")
    for key, value in scalars.items():
        lines.append(f"{key} = {_toml_value(value)}")
    for key, value in nested.items():
        lines.append("")
        _dump_section(lines, f"{section}.{key}", value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'
