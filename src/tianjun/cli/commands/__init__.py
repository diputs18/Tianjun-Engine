"""Command handler package for Tianjun CLI convergence.

The public command behavior is still preserved by ``tianjun.cli.main``. Future
small PRs can move one command at a time into this package while reusing
``tianjun.cli.context`` and ``tianjun.cli.parser``.
"""

COMMAND_GROUPS = [
    "serve",
    "chat",
    "llm_check",
    "mcp_server",
    "agent",
    "real_agent",
    "sim_backend",
    "runtime_demo",
    "secrets",
]
