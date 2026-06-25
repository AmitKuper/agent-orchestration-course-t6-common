"""Shared server state and auth helpers for the MCP server."""

from __future__ import annotations

import json
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


def patch_state_game_id(game_id: str) -> None:
    """Fix the game_id field in state.json after a directory rename.

    sdk_new_game generates an auto ID; when the directory is renamed to the
    agreed game_id, state.json still holds the old ID. This corrects it.

    Args:
        game_id: The agreed identifier (also the directory name).
    """
    state_file = games_base() / game_id / "state.json"
    if state_file.exists():
        data = json.loads(state_file.read_text(encoding="utf-8"))
        data["game_id"] = game_id
        state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
