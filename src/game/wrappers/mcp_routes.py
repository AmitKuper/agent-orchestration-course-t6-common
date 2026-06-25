"""Custom HTTP routes for the MCP server — health check only.

All game synchronisation (receive_action, get_hash, propose_match_tool) is
now exposed as standard MCP Tools in mcp_sync_tools.py so every inter-server
call uses the real MCP protocol instead of ad-hoc REST.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_routes(mcp: FastMCP) -> None:
    """Register the /health route on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance to attach the route to.
    """
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        """Health check endpoint used by the orchestrator before match start.

        Returns:
            JSON {"status": "ok"} with HTTP 200.
        """
        return JSONResponse({"status": "ok"})
