"""Persistence helpers: state.json read/write, game.log JSONL append.

Log-writing functions (append_setup_log, append_log, append_terminal_log)
live in log_writer.py and are re-exported here for backwards compatibility.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

# Re-export log writers so existing callers need no import changes.
from game.log_writer import append_log, append_setup_log, append_terminal_log

if TYPE_CHECKING:
    from game.game import Game

__all__ = [
    "game_dir", "generate_game_id", "save_state", "load_state",
    "append_setup_log", "append_log", "append_terminal_log",
]

_DEFAULT_GAMES_DIR = Path("games")


def game_dir(game_id: str, base: Path | None = None) -> Path:
    """Return the directory for a specific game, creating it if necessary.

    Args:
        game_id: The game identifier.
        base: Optional override for the games root directory.

    Returns:
        Path to the game's directory (created if absent).
    """
    root = base or _DEFAULT_GAMES_DIR
    root.mkdir(parents=True, exist_ok=True)
    d = root / game_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_game_id() -> str:
    """Generate a unique 8-character game ID."""
    return uuid.uuid4().hex[:8]


def save_state(game: Game, base: Path | None = None) -> None:
    """Persist game state to games/<game_id>/state.json.

    Args:
        game: The Game instance to persist.
        base: Optional override for the games root directory.
    """
    data = game.to_dict()
    path = game_dir(data["game_id"], base) / "state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(game_id: str, base: Path | None = None) -> Game:
    """Load a Game from games/<game_id>/state.json.

    Args:
        game_id: The game identifier.
        base: Optional override for the games root directory.

    Raises:
        FileNotFoundError: If no state.json exists for the given game_id.
    """
    from game.game import Game  # local import avoids circular dependency

    path = (base or _DEFAULT_GAMES_DIR) / game_id / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No game state found for game_id={game_id!r}")
    return Game.from_dict(json.loads(path.read_text(encoding="utf-8")))
