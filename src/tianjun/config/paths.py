from __future__ import annotations

import os
import platform
import re
from pathlib import Path

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")


def user_config_dir() -> Path:
    """Return a cross-platform per-user Tianjun configuration directory."""
    system = platform.system().lower()
    if system == "windows":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "Tianjun"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "tianjun"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tianjun"


def user_state_dir() -> Path:
    """Return a cross-platform per-user Tianjun state directory."""
    system = platform.system().lower()
    if system == "windows":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "Tianjun"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "tianjun"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "tianjun"


def project_root(start: str | os.PathLike[str] | None = None) -> Path:
    """Best-effort project root used by portable example configs.

    ``tianjun.example.toml`` is usually copied from ``configs/`` to the project
    root. Using ``${TIANJUN_HOME}`` avoids brittle ``../`` paths in both cases.
    The environment variable still wins when deployments keep configs outside
    the source tree.
    """
    if os.environ.get("TIANJUN_HOME"):
        return Path(os.environ["TIANJUN_HOME"]).expanduser().resolve()

    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "tianjun").exists():
            return candidate
        if (candidate / "src" / "tianjun").exists() and (candidate / "examples").exists():
            return candidate
    return current


def expand_config_value(value: str, *, base_dir: Path | None = None) -> str:
    """Expand env placeholders while providing Tianjun platform defaults."""
    defaults = {
        "TIANJUN_CONFIG_DIR": str(user_config_dir()),
        "TIANJUN_STATE_DIR": str(user_state_dir()),
        "TIANJUN_HOME": str(project_root(base_dir)),
    }

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        fallback = match.group(2)
        if name in os.environ:
            return os.environ[name]
        if name in defaults:
            return defaults[name]
        return fallback if fallback is not None else match.group(0)

    return os.path.expanduser(_ENV_PATTERN.sub(replace, value))


def resolve_path(value: str | os.PathLike[str] | None, *, base_dir: Path | None = None) -> Path | None:
    """Resolve a user-facing path consistently across platforms.

    Relative paths are resolved from the configuration file directory when a
    config file was loaded, otherwise from the current working directory. For
    repository resources that must survive copying the template config, prefer
    ``${TIANJUN_HOME}/...`` in TOML.
    """
    if value in (None, ""):
        return None
    raw = expand_config_value(os.fspath(value), base_dir=base_dir)
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base_dir or Path.cwd()).joinpath(path).resolve()
