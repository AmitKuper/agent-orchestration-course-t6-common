"""GameState dataclass — the full internal state persisted to state.json."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GameState:
    """Full canonical game state, serialized to state.json after every action."""

    game_id: str
    grid_cols: int
    grid_rows: int
    cop_pos: tuple[int, int]
    thief_pos: tuple[int, int]
    barriers: list[tuple[int, int]]
    round: int
    turn: int
    barriers_placed: int
    max_moves: int
    max_barriers: int
    game_over: bool
    winner: str | None
    win_reason: str | None
    mechanics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GameState:
        """Restore from dict (e.g. loaded from state.json)."""
        d = dict(d)
        d["cop_pos"] = tuple(d["cop_pos"])
        d["thief_pos"] = tuple(d["thief_pos"])
        d["barriers"] = [tuple(b) for b in d["barriers"]]
        # Backwards compatibility: add turn=0 if loading an older state.json
        d.setdefault("turn", 0)
        return cls(**d)
