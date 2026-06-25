"""Action types and parsing for the Cop & Thief game."""

from __future__ import annotations

from dataclasses import dataclass

from game.constants import ALL_ACTIONS, BARRIER_ACTION, DIRECTIONS, STAY_ACTION


@dataclass(frozen=True)
class MoveAction:
    """A directional move action."""

    direction: str

    def __post_init__(self) -> None:
        """Validate direction on construction."""
        if self.direction not in DIRECTIONS:
            raise ValueError(f"Invalid direction: {self.direction!r}")

    @property
    def delta(self) -> tuple[int, int]:
        """Return (col_delta, row_delta) for this direction."""
        return DIRECTIONS[self.direction]


@dataclass(frozen=True)
class BarrierAction:
    """Place a barrier on the cop's current cell."""

    pass


@dataclass(frozen=True)
class StayAction:
    """Thief stays in place for one turn (no position change)."""

    pass


def parse_action(raw: str) -> MoveAction | BarrierAction | StayAction:
    """Parse a raw action string into a typed action object.

    Args:
        raw: Action string, e.g. "N", "NE", "BARRIER", "STAY".

    Returns:
        MoveAction, BarrierAction, or StayAction instance.

    Raises:
        ValueError: If the action string is not recognized.
    """
    action = raw.strip().upper()
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unknown action: {raw!r}. Valid actions: {sorted(ALL_ACTIONS)}")
    if action == BARRIER_ACTION:
        return BarrierAction()
    if action == STAY_ACTION:
        return StayAction()
    return MoveAction(direction=action)
