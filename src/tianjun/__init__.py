"""Tianjun Engine core package.

Runtime boundaries:

- ``domain``: scheduling entities and value objects
- ``scheduling``: closed-loop scheduling engine
- ``application``: control-plane use cases
- ``tools``: unified agent/MCP/Dashboard tool surface
- ``chat``: safe conversation orchestration over the unified tools
- ``interfaces``: HTTP server and dashboard surface
- ``node_agent`` / ``simulation``: real and simulated execution agents
- ``policy``: compute-network policy generation, simulation and feedback
- ``inventory``: config-driven resource and workload inventory
"""

__version__ = "0.1.0"
