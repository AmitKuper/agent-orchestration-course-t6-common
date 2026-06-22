"""FastMCP tool registrations for the Cop & Thief game engine.

Run as an MCP server:
    python -m game.wrappers.mcp_tools

Authentication: set MCP_API_KEY (client) and MCP_ALLOWED_API_KEYS (server, comma-separated).
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from game.sdk.sdk import get_state as sdk_get_state
from game.sdk.sdk import new_game as sdk_new_game
from game.sdk.sdk import state_hash as sdk_hash
from game.sdk.sdk import submit_action as sdk_submit_action

mcp = FastMCP(
    name="cop-thief-game",
    instructions=(
        "You are a player in the Cop & Thief pursuit game. "
        "Use the tools to interact with the game engine. "
        "Always call get_state after submit_action to see the updated board."
    ),
)


@mcp.tool()
def new_game(
    grid_cols: int,
    grid_rows: int,
    cop_col: int,
    cop_row: int,
    thief_col: int,
    thief_row: int,
) -> str:
    """Create a new game instance and return the game_id.

    Args:
        grid_cols: Number of columns.
        grid_rows: Number of rows.
        cop_col: Cop starting column (0-indexed).
        cop_row: Cop starting row (0-indexed).
        thief_col: Thief starting column (0-indexed).
        thief_row: Thief starting row (0-indexed).

    Returns:
        JSON string {"game_id": "<id>"}.
    """
    try:
        result = sdk_new_game(
            grid_size=(grid_cols, grid_rows),
            cop_pos=(cop_col, cop_row),
            thief_pos=(thief_col, thief_row),
        )
        return json.dumps(result)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def submit_action(game_id: str, actor: str, action: str) -> str:
    """Submit a move or BARRIER action.

    Args:
        game_id: Game identifier from new_game.
        actor: "cop" or "thief".
        action: Direction (N/NE/E/SE/S/SW/W/NW) or BARRIER (cop only).

    Returns:
        JSON ActionResult: success, error, game_over, winner, win_reason.
    """
    try:
        result = sdk_submit_action(game_id, actor, action)
        return result.to_json()
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def get_state(game_id: str, actor: str) -> str:
    """Get current observable state for an actor.

    Args:
        game_id: Game identifier.
        actor: "cop" or "thief".

    Returns:
        JSON ObservationState: actor, round, my_pos, opponent_pos,
        barriers, legal_moves, barriers_remaining.
    """
    try:
        obs = sdk_get_state(game_id, actor)
        return obs.to_json()
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def game_hash(game_id: str) -> str:
    """Return canonical state hash for cross-engine validation.

    Args:
        game_id: Game identifier.

    Returns:
        JSON {"hash": "<8-char-hex>"}.
    """
    try:
        h = sdk_hash(game_id)
        return json.dumps({"hash": h})
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run()
