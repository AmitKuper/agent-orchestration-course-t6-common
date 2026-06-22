"""JSON-serializable dataclasses for game inputs and outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class ActionResult:
    """Result returned by Game.submit_action()."""

    success: bool
    error: str | None
    game_over: bool
    winner: str | None
    win_reason: str | None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, d: dict) -> ActionResult:
        """Deserialize from dict."""
        return cls(**d)


@dataclass
class ObservationState:
    """Game state from the perspective of one actor."""

    actor: str
    round: int
    my_pos: tuple[int, int]
    opponent_pos: tuple[int, int] | None
    barriers: list[tuple[int, int]]
    legal_moves: list[str]
    barriers_remaining: int | None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, d: dict) -> ObservationState:
        """Deserialize from dict."""
        d = dict(d)
        d["my_pos"] = tuple(d["my_pos"])
        if d["opponent_pos"] is not None:
            d["opponent_pos"] = tuple(d["opponent_pos"])
        d["barriers"] = [tuple(b) for b in d["barriers"]]
        return cls(**d)
