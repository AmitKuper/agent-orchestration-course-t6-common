"""Persistence helpers: state.json read/write and game.log JSONL append."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.game import Game
    from game.state import ActionResult

_DEFAULT_GAMES_DIR = Path("games")


def games_dir(base: Path | None = None) -> Path:
    """Return the root games directory, creating it if necessary."""
    root = base or _DEFAULT_GAMES_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def game_dir(game_id: str, base: Path | None = None) -> Path:
    """Return the directory for a specific game, creating it if necessary."""
    d = games_dir(base) / game_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_game_id() -> str:
    """Generate a unique 8-character game ID."""
    return uuid.uuid4().hex[:8]


def save_state(game: Game, base: Path | None = None) -> None:
    """Persist game state to games/<game_id>/state.json.

    Args:
        game: The Game instance to save.
        base: Optional override for the games root directory.
    """
    data = game.to_dict()
    path = game_dir(data["game_id"], base) / "state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(game_id: str, base: Path | None = None) -> Game:
    """Load a Game instance from games/<game_id>/state.json.

    Args:
        game_id: The game identifier.
        base: Optional override for the games root directory.

    Returns:
        The restored Game instance.

    Raises:
        FileNotFoundError: If no state.json exists for the given game_id.
    """
    from game.game import Game  # local import to avoid circular dependency

    path = games_dir(base) / game_id / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No game state found for game_id={game_id!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Game.from_dict(data)


def append_log(
    game_id: str,
    actor: str,
    action: str,
    result: ActionResult,
    extra: dict[str, Any] | None = None,
    base: Path | None = None,
) -> None:
    """Append a JSONL entry to games/<game_id>/game.log.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".
        action: The action string submitted.
        result: The ActionResult returned by submit_action.
        extra: Optional additional fields to include in the log entry.
        base: Optional override for the games root directory.
    """
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "game_id": game_id,
        "actor": actor,
        "action": action,
        "success": result.success,
        "error": result.error,
        "game_over": result.game_over,
        "winner": result.winner,
        "win_reason": result.win_reason,
    }
    if extra:
        entry.update(extra)

    log_path = game_dir(game_id, base) / "game.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
