"""CrewAI @tool wrappers for the Cop & Thief game engine.

Each tool loads game state from disk via game_id, calls one SDK method,
and returns a JSON string suitable for LLM consumption.
"""

from __future__ import annotations

import json

from crewai.tools import tool

from game.sdk.sdk import get_state as sdk_get_state
from game.sdk.sdk import new_game as sdk_new_game
from game.sdk.sdk import submit_action as sdk_submit_action


@tool("new_game")
def new_game(  # noqa: PLR0913
    grid_cols: int,
    grid_rows: int,
    cop_col: int,
    cop_row: int,
    thief_col: int,
    thief_row: int,
) -> str:
    """Create a new Cop & Thief game.

    Args:
        grid_cols: Number of columns in the grid.
        grid_rows: Number of rows in the grid.
        cop_col: Cop starting column (0-indexed).
        cop_row: Cop starting row (0-indexed).
        thief_col: Thief starting column (0-indexed).
        thief_row: Thief starting row (0-indexed).

    Returns:
        JSON string with {"game_id": "<id>"}.
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


@tool("submit_action")
def submit_action(game_id: str, actor: str, action: str) -> str:
    """Submit a move or barrier placement for an actor.

    Valid actions: N, NE, E, SE, S, SW, W, NW (move), BARRIER (cop only).

    Args:
        game_id: The game identifier returned by new_game.
        actor: "cop" or "thief".
        action: The action string (direction or BARRIER).

    Returns:
        JSON string with ActionResult fields:
        success, error, game_over, winner, win_reason.
    """
    try:
        result = sdk_submit_action(game_id, actor, action)
        return result.to_json()
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})


@tool("get_state")
def get_state(game_id: str, actor: str) -> str:
    """Get the current observable game state for an actor.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".

    Returns:
        JSON string with ObservationState fields:
        actor, round, my_pos, opponent_pos, barriers, legal_moves, barriers_remaining.
    """
    try:
        obs = sdk_get_state(game_id, actor)
        return obs.to_json()
    except (FileNotFoundError, ValueError) as exc:
        return json.dumps({"error": str(exc)})
