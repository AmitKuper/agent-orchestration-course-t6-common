"""Shared server state and auth helpers for the MCP server."""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request

from game.wrappers.mcp_auth import validate_key

# Module-level state dict — populated at server startup and on match accept.
server_state: dict = {"games_base": Path("games"), "matches": {}}


def games_base() -> Path:
    """Return the configured games root directory."""
    return server_state["games_base"]


def auth_ok(request: Request) -> bool:
    """Return True if the inbound request carries a valid API key.

    Checks X-API-Key header first, then Authorization Bearer token.

    Args:
        request: Incoming Starlette request.
    """
    bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
    key = request.headers.get("X-API-Key") or bearer
    return validate_key(key)
