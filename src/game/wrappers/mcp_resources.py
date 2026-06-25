"""MCP resource registrations — live game config and state resources.

Exposes game://config (static) and game://{game_id}/state/{actor} (dynamic)
as FastMCP resources so the LLM client can read them directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "config.json"

_CONFIG_DEFAULTS: dict = {
    "grid_size": [5, 5], "max_moves": 25, "max_barriers": 5,
    "partial_observation": True, "view_radius": 2,
    "turn_timeout_seconds": 30, "max_illegal_retries": 2,
    "max_consecutive_forfeits": 3,
}


def _load_game_config() -> dict:
    """Load game config from config/config.json, falling back to built-in defaults."""
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open() as fh:
            return json.load(fh)
    return dict(_CONFIG_DEFAULTS)


_GAME_CONFIG: dict = _load_game_config()


def register_resources(mcp: FastMCP) -> None:
    """Register game://config and game://{game_id}/state/{actor} on the server.

    Args:
        mcp: The FastMCP server instance to attach resources to.
    """
    @mcp.resource("game://config")
    def game_config() -> str:
        """Active game configuration: grid, rules limits, and observability settings.

        Returns:
            JSON string of the game configuration dict.
        """
        return json.dumps(_GAME_CONFIG, indent=2)

    @mcp.resource("game://{game_id}/state/{actor}")
    def game_state(game_id: str, actor: str) -> str:
        """Live ObservationState for the given actor in the given game.

        Returns the partial observation — opponent position is hidden when
        outside view_radius (Chebyshev distance = 2).

        Args:
            game_id: The game identifier.
            actor: "cop" or "thief".

        Returns:
            JSON string of the ObservationState dict, or {"error": ...} on failure.
        """
        from game.sdk.sdk import get_state as sdk_get_state
        from game.wrappers.mcp_state import games_base

        try:
            obs = sdk_get_state(game_id, actor, games_base())
            return json.dumps(asdict(obs), indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
