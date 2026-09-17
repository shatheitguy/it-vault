"""IT-Vault MCP server: the asset register and helpdesk as agent tools."""

# Only `main` is re-exported, deliberately. Re-exporting the MCPServer object
# as `server` shadowed the `itvault_mcp.server` submodule of the same name, so
# `import itvault_mcp.server` handed back the object instead of the module --
# which broke importing it the ordinary way.
from .server import main

__all__ = ["main"]
