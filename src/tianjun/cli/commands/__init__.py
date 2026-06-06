"""Command handler package for Tianjun CLI commands.

The package entry point parses arguments, loads configuration, and dispatches
to these modules. Command business logic should live here, not in
``tianjun.cli.__init__``.
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
