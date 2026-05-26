from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from .paths import project_root, resolve_path, user_config_dir
from .schema import ConfigSource, deep_merge, default_payload


DEFAULT_CONFIG_FILENAMES = ("tianjun.toml",)


def find_config_file() -> Path | None:
    env_path = os.environ.get("TIANJUN_CONFIG")
    if env_path:
        candidate = resolve_path(env_path)
        return candidate if candidate and candidate.exists() else candidate
    for candidate in (Path.cwd() / name for name in DEFAULT_CONFIG_FILENAMES):
        if candidate.exists():
            return candidate
    user_candidate = user_config_dir() / "tianjun.toml"
    if user_candidate.exists():
        return user_candidate
    return None


class TianjunConfig:
    """Layered application configuration.

    The object keeps compatibility with the old dotted-path ``get`` API while
    making TOML and cross-platform path resolution the default.
    """

    def __init__(self, payload: dict[str, Any] | None = None, *, source_path: Path | None = None) -> None:
        self.payload = deep_merge(default_payload(), payload or {})
        self.source_path = source_path
        self.base_dir = source_path.parent if source_path else Path.cwd()
        self.source = ConfigSource(path=str(source_path) if source_path else None, loaded=source_path is not None)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "TianjunConfig":
        config_path = resolve_path(path) if path else find_config_file()
        if config_path is None:
            _load_project_env(Path.cwd())
            return cls()
        if not config_path.exists():
            raise FileNotFoundError(f"Tianjun config file not found: {config_path}")
        _load_project_env(config_path)
        return cls(_read_config(config_path), source_path=config_path)

    def get(self, dotted_path: str, default: Any = None) -> Any:
        current: Any = self.payload
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def path(self, dotted_path: str, default: Any = None) -> Path | None:
        value = self.get(dotted_path, default)
        return resolve_path(value, base_dir=self.base_dir)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def _read_config(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
    if suffix == ".json":
        # Legacy compatibility only; new projects should use TOML.
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported config file type {suffix!r}; use .toml")


def _load_project_env(anchor: Path) -> None:
    """Load .env files without overriding shell-provided variables.

    This keeps Windows/PowerShell usage predictable: users can either set
    ``DEEPSEEK_API_KEY`` in the shell or put it in ``.env`` at the project root.
    """
    candidates: list[Path] = []
    if anchor.is_file():
        candidates.append(anchor.parent / ".env")
    else:
        candidates.append(anchor / ".env")
    candidates.append(project_root(anchor) / ".env")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        load_env_file(resolved, override=False)


def load_env_file(path: str | Path, *, override: bool = False) -> dict[str, str]:
    """Load a small dotenv-style file.

    Supported syntax is intentionally conservative: ``KEY=value`` with optional
    single/double quotes and ``#`` comments. Existing environment variables win
    unless ``override=True`` is passed.
    """
    env_path = Path(path)
    loaded: dict[str, str] = {}
    if not env_path.exists() or not env_path.is_file():
        return loaded
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
    return default


def config_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def config_path(value: Any, *, base_dir: Path | None = None) -> Path | None:
    return resolve_path(None if value is None else str(value), base_dir=base_dir)
