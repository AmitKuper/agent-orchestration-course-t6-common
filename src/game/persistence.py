"""Persistence helpers: state.json read/write, game.log JSONL append."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from game.constants import compute_scores

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
    """Persist game state to games/<game_id>/state.json."""
    data = game.to_dict()
    path = game_dir(data["game_id"], base) / "state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(game_id: str, base: Path | None = None) -> Game:
    """Load a Game instance from games/<game_id>/state.json.

    Raises:
        FileNotFoundError: If no state.json exists for the given game_id.
    """
    from game.game import Game  # local import to avoid circular dependency

    path = games_dir(base) / game_id / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"No game state found for game_id={game_id!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Game.from_dict(data)


def _write_log_line(game_id: str, entry: dict, base: Path | None) -> None:
    """Append one JSONL line to games/<game_id>/game.log."""
    log_path = game_dir(game_id, base) / "game.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def append_log(
    game_id: str,
    actor: str,
    action: str,
    result: ActionResult,
    from_pos: tuple[int, int],
    to_pos: tuple[int, int],
    game: Game,
    base: Path | None = None,
) -> None:
    """Append a per-turn JSONL entry (PRD §4.1 format) to game.log.

    Args:
        game_id: The game identifier.
        actor: "cop" or "thief".
        action: Raw action string (direction or BARRIER).
        result: ActionResult from submit_action.
        from_pos: Actor's position before the action.
        to_pos: Actor's position after the action (unchanged if action failed).
        game: Updated Game instance (used for state_after snapshot).
        base: Optional override for the games root directory.
    """
    is_barrier = action.upper() == "BARRIER"
    state = game.to_dict()
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "game_id": game_id,
        "turn": state["turn"],
        "actor": actor,
        "action": "barrier" if is_barrier else "move",
        "from": list(from_pos),
        "to": list(to_pos),
        "barrier_at": list(from_pos) if is_barrier and result.success else None,
        "message": None,
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
    """Append the terminal summary entry to game.log on game-over.

    Args:
        game_id: The game identifier.
        result: The game-over ActionResult.
        game: Final Game instance (for round count, barriers used, mechanics).
        base: Optional override for the games root directory.
    """
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
