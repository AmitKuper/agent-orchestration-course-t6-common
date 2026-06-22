"""Unit tests for action parsing."""

import pytest

from game.actions import BarrierAction, MoveAction, parse_action
from game.constants import DIRECTIONS


def test_parse_all_move_directions() -> None:
    """All 8 direction strings parse to MoveAction with correct delta."""
    for direction, delta in DIRECTIONS.items():
        action = parse_action(direction)
        assert isinstance(action, MoveAction)
        assert action.direction == direction
        assert action.delta == delta


def test_parse_barrier() -> None:
    """'BARRIER' parses to BarrierAction."""
    action = parse_action("BARRIER")
    assert isinstance(action, BarrierAction)


def test_parse_case_insensitive() -> None:
    """Action parsing is case-insensitive."""
    assert isinstance(parse_action("n"), MoveAction)
    assert isinstance(parse_action("barrier"), BarrierAction)


def test_parse_unknown_raises() -> None:
    """Unknown action raises ValueError."""
    with pytest.raises(ValueError, match="Unknown action"):
        parse_action("JUMP")


def test_move_action_invalid_direction() -> None:
    """Constructing MoveAction with bad direction raises ValueError."""
    with pytest.raises(ValueError, match="Invalid direction"):
        MoveAction(direction="JUMP")
