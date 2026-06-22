"""SDK entry point — single interface for all external callers (CLI, CrewAI, MCP).

All callers load state from disk, invoke one method, and save the result back.
The Game object is stateless between calls; canonical state lives in games/<game_id>/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from game.constants import COP
from game.game import Game
from game.persistence import (
    append_log,
    append_setup_log,
    append_terminal_log,
    generate_game_id,
    load_state,
    save_state,
)
from game.state import ActionResult, ObservationState


def new_game(
    grid_size: tuple[int, int],
    cop_pos: tuple[int, int],
    thief_pos: tuple[int, int],
    mechanics: dict[str, Any] | None = None,
    seed: int | None = None,
    games_base: Path | None = None,
) -> dict[str, str]:
    """Create a new game, persist it, and write the setup log entry.

    Args:
        grid_size: (cols, rows) of the grid.
        cop_pos: Starting (col, row) of the cop, 0-indexed.
        thief_pos: Starting (col, row) of the thief, 0-indexed.
        mechanics: Optional mechanics overrides.
        seed: Random seed used to derive positions (logged for replay).
        games_base: Optional override for the games root directory.

    Returns:
        Dict with "game_id" key.

    Raises:
        ValueError: If positions are invalid.
    """
    game_id = generate_game_id()
    mech = mechanics or {}
    game = Game.new(game_id, grid_size, cop_pos, thief_pos, mech)
    save_state(game, games_base)
    append_setup_log(game_id, seed, mech, grid_size, cop_pos, thief_pos, base=games_base)
    return {"game_id": game_id}


def submit_action(
    game_id: str,
    actor: str,
    action: str,
    message: str | None = None,
    games_base: Path | None = None,
) -> ActionResult:
    """Load game, submit action, persist state, and write log entry.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".
        action: Action string (direction or BARRIER).
        message: Free-text NL message the agent sent this turn.
        games_base: Optional override for the games root directory.

    Returns:
        ActionResult dataclass.
    """
    game = load_state(game_id, games_base)
    from_pos = game._state.cop_pos if actor == COP else game._state.thief_pos
    result = game.submit_action(actor, action)
    to_pos = game._state.cop_pos if actor == COP else game._state.thief_pos

    if result.success:
        save_state(game, games_base)

    append_log(game_id, actor, action, result, from_pos, to_pos, game,
               message=message, base=games_base)

    if result.game_over:
        append_terminal_log(game_id, result, game, base=games_base)

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
    """
    return load_state(game_id, games_base).get_state(actor)


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
    return load_state(game_id, games_base).state_hash()
