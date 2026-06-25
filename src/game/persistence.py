"""Persistence helpers: state.json read/write, game.log JSONL append."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from game.constants import compute_scores

if TYPE_CHECKING:
    from game.game import Game
    from game.state import ActionResult

_DEFAULT_GAMES_DIR = Path("games")


def game_dir(game_id: str, base: Path | None = None) -> Path:
    """Return the directory for a specific game, creating it if necessary."""
    root = base or _DEFAULT_GAMES_DIR
    root.mkdir(parents=True, exist_ok=True)
    d = root / game_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_game_id() -> str:
    """Generate a unique 8-character game ID."""
    return uuid.uuid4().hex[:8]


def save_state(game: Game, base: Path | None = None) -> None:
    """Persist game state to games/<game_id>/state.json."""
    data = game.to_dict()
    path = game_dir(data["game_id"], base) / "state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(game_id: str, base: Path | None = None) -> Game:
    """Load a Game from games/<game_id>/state.json.

    Raises:
        FileNotFoundError: If no state.json exists for the given game_id.
    """
    from game.game import Game  # local import avoids circular dependency

    path = (base or _DEFAULT_GAMES_DIR) / game_id / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No game state found for game_id={game_id!r}")
    return Game.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _write_log_line(game_id: str, entry: dict, base: Path | None) -> None:
    """Append one JSONL line to games/<game_id>/game.log."""
    log_path = game_dir(game_id, base) / "game.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def append_setup_log(
    game_id: str,
    seed: int | None,
    mechanics: dict,
    grid_size: tuple[int, int],
    cop_pos: tuple[int, int],
    thief_pos: tuple[int, int],
    base: Path | None = None,
) -> None:
    """Append the initial setup entry to game.log when a game is created.

    Args:
        game_id: The game identifier.
        seed: Random seed used to derive start positions (None if manual).
        mechanics: Agreed game mechanics dict.
        grid_size: (cols, rows) of the grid.
        cop_pos: Cop starting position (col, row).
        thief_pos: Thief starting position (col, row).
        base: Optional override for the games root directory.
    """
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "game_id": game_id,
        "type": "setup",
        "player_name": os.environ.get("PLAYER_NAME", ""),
        "seed": seed,
        "grid": list(grid_size),
        "cop": list(cop_pos),
        "thief": list(thief_pos),
        "mechanics": mechanics,
    }
    _write_log_line(game_id, entry, base)


def append_log(
    game_id: str,
    actor: str,
    action: str,
    result: ActionResult,
    from_pos: tuple[int, int],
    to_pos: tuple[int, int],
    game: Game,
    message: str | None = None,
    base: Path | None = None,
) -> None:
    """Append a per-turn JSONL entry (PRD §4.1 format) to game.log."""
    is_barrier = action.upper() == "BARRIER"
    state = game.to_dict()
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "game_id": game_id,
        "type": "turn",
        "turn": state["turn"],
        "actor": actor,
        "action": "barrier" if is_barrier else "move",
        "from": list(from_pos),
        "to": list(to_pos),
        "barrier_at": list(from_pos) if is_barrier and result.success else None,
        "message": message,
        "success": result.success,
        "error": result.error,
        "state_after": {
            "cop": list(state["cop_pos"]),
            "thief": list(state["thief_pos"]),
            "barriers": [list(b) for b in state["barriers"]],
        },
    }
    _write_log_line(game_id, entry, base)


def append_terminal_log(
    game_id: str,
    result: ActionResult,
    game: Game,
    base: Path | None = None,
) -> None:
    """Append the terminal summary entry to game.log on game-over."""
    state = game.to_dict()
    scores = compute_scores(result.winner, state.get("mechanics", {}))
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "game_id": game_id,
        "type": "terminal",
        "winner": result.winner,
        "win_reason": result.win_reason,
        "rounds": state["round"],
        "barriers_used": state["barriers_placed"],
        "scores": scores,
    }
    _write_log_line(game_id, entry, base)
