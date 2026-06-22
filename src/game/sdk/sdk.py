"""SDK entry point — single interface for all external callers (CLI, CrewAI, MCP).

All callers load game state from disk, call one method, and save the result back.
The Game object is stateless between calls; state lives in games/<game_id>/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from game.game import Game
from game.persistence import append_log, generate_game_id, load_state, save_state
from game.state import ActionResult, ObservationState


def new_game(
    grid_size: tuple[int, int],
    cop_pos: tuple[int, int],
    thief_pos: tuple[int, int],
    mechanics: dict[str, Any] | None = None,
    games_base: Path | None = None,
) -> dict[str, str]:
    """Create a new game and persist it to disk.

    Args:
        grid_size: (cols, rows) of the grid.
        cop_pos: Starting (col, row) of the cop, 0-indexed.
        thief_pos: Starting (col, row) of the thief, 0-indexed.
        mechanics: Optional mechanics overrides.
        games_base: Optional override for the games root directory.

    Returns:
        Dict with "game_id" key.

    Raises:
        ValueError: If positions are invalid.
    """
    game_id = generate_game_id()
    game = Game.new(game_id, grid_size, cop_pos, thief_pos, mechanics)
    save_state(game, games_base)
    return {"game_id": game_id}


def submit_action(
    game_id: str,
    actor: str,
    action: str,
    games_base: Path | None = None,
) -> ActionResult:
    """Load game, submit action, persist updated state, append log entry.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".
        action: Action string.
        games_base: Optional override for the games root directory.

    Returns:
        ActionResult dataclass.
    """
    game = load_state(game_id, games_base)
    result = game.submit_action(actor, action)
    if result.success:
        save_state(game, games_base)
    append_log(game_id, actor, action, result, base=games_base)
    return result


def get_state(
    game_id: str,
    actor: str,
    games_base: Path | None = None,
) -> ObservationState:
    """Load game and return actor-scoped observation state.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".
        games_base: Optional override for the games root directory.

    Returns:
        ObservationState dataclass.
    """
    game = load_state(game_id, games_base)
    return game.get_state(actor)


def state_hash(
    game_id: str,
    games_base: Path | None = None,
) -> str:
    """Return canonical state hash for the given game.

    Args:
        game_id: The game identifier.
        games_base: Optional override for the games root directory.

    Returns:
        8-character hex string.
    """
    game = load_state(game_id, games_base)
    return game.state_hash()
