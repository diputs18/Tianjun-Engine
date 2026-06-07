from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise AssertionError(message)


def assert_cli_entry_is_dispatch_only() -> None:
    source = read("src/tianjun/cli/__init__.py")
    forbidden = [
        "run_until_idle(",
        "run_real_node_agent(",
        "serve_forever(",
        "input(\"> \")",
    ]
    for token in forbidden:
        if token in source:
            fail(f"cli/__init__.py contains command-body token: {token}")
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    required = {
        "add_llm_options",
        "resolved_llm_settings",
        "add_model_options",
        "resolved_model_dir",
        "require_model",
        "resolved_path_setting",
        "build_parser",
        "main",
        "dispatch",
    }
    if not required.issubset(names):
        fail("cli/__init__.py is missing expected parser/context/dispatch functions")


def assert_command_handlers_exist() -> None:
    commands = {
        "agent.py",
        "chat.py",
        "llm_check.py",
        "mcp_server.py",
        "real_agent.py",
        "runtime_demo.py",
        "secrets.py",
        "serve.py",
    }
    found = {path.name for path in (ROOT / "src/tianjun/cli/commands").glob("*.py")}
    missing = commands - found
    if missing:
        fail(f"missing CLI command handlers: {sorted(missing)}")


def assert_legacy_routes_are_single_source() -> None:
    server = read("src/tianjun/interfaces/http/server.py")
    if "def _legacy_" in server or 'path == "/intent"' in server or 'path == "/hermes/chat"' in server:
        fail("server.py contains legacy route implementation instead of delegating")
    legacy = read("src/tianjun/interfaces/http/legacy_routes.py")
    for token in ['path == "/intent"', 'path == "/chat"', 'path == "/hermes/chat"', 'path == "/hermes/chat/stream"']:
        if token not in legacy:
            fail(f"legacy_routes.py is missing {token}")
    if 'payload.get("dry_run", True)' not in legacy:
        fail("legacy /intent must default to preview")


def assert_dashboard_uses_official_routes() -> None:
    js = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/tianjun/interfaces/dashboard/static/js").rglob("*.js"))
    forbidden = ['"/intent"', '"/chat"', '"/hermes/']
    for token in forbidden:
        if token in js:
            fail(f"Dashboard JavaScript contains legacy route token: {token}")


def assert_dependency_single_source() -> None:
    requirements = read("requirements.txt")
    forbidden = ["pytest>=", "torch>=", "fastmcp>=", "tomli>="]
    for token in forbidden:
        if token in requirements:
            fail(f"requirements.txt duplicates dependency fact: {token}")
    pyproject = read("pyproject.toml")
    if "[project.optional-dependencies]" not in pyproject:
        fail("pyproject.toml is missing optional dependency declarations")


def assert_mcp_contract_alignment() -> None:
    from tianjun.tools import MCP_TOOL_NAMES, tianjun_tool_contract

    contract = tianjun_tool_contract()
    if set(contract["mcp_tools"]) != set(MCP_TOOL_NAMES):
        fail("MCP tool contract does not match MCP_TOOL_NAMES")
    if "analyze_user_intent" in MCP_TOOL_NAMES:
        fail("analyze_user_intent must remain internal, not MCP-exposed")


def main() -> int:
    checks = [
        assert_cli_entry_is_dispatch_only,
        assert_command_handlers_exist,
        assert_legacy_routes_are_single_source,
        assert_dashboard_uses_official_routes,
        assert_dependency_single_source,
        assert_mcp_contract_alignment,
    ]
    for check in checks:
        check()
    print("convergence checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
