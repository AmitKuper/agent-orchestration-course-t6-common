"""Unit tests for game.agent.agent."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from game.agent.agent import Agent, TechnicalLossError
from game.sdk import sdk
from game.state import ActionResult, ObservationState


def _obs(**kwargs: object) -> ObservationState:
    """Build a minimal ObservationState."""
    defaults = dict(
        actor="cop", round=1, my_pos=(0, 0), opponent_pos=(4, 4),
        barriers=[], legal_moves=["E", "S"], barriers_remaining=3,
    )
    return ObservationState(**{**defaults, **kwargs})


def _result(success: bool, game_over: bool = False) -> ActionResult:
    """Build an ActionResult."""
    return ActionResult(success=success, error=None if success else "illegal",
                        game_over=game_over, winner=None, win_reason=None)


def _make_agent(wrapper: object, actor: str = "cop",
                games_base: Path | None = None,
                max_retries: int = 2, max_forfeits: int = 3) -> Agent:
    """Helper to build an Agent."""
    return Agent(wrapper, actor, max_illegal_retries=max_retries,
                 max_consecutive_forfeits=max_forfeits, games_base=games_base)


def test_take_turn_success_on_first_attempt() -> None:
    """Successful action resets consecutive_forfeits and returns result."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        wrapper = MagicMock()
        wrapper.get_action.return_value = ("E", "moving east")
        agent = _make_agent(wrapper, "cop", games_base=base)

        result = agent.take_turn(gid)
        assert result.success
        assert agent._consecutive_forfeits == 0


def test_take_turn_retries_on_illegal_then_succeeds() -> None:
    """Illegal action triggers retry; succeeds on second attempt."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        wrapper = MagicMock()
        wrapper.get_action.side_effect = [("N", "north"), ("E", "east")]
        agent = _make_agent(wrapper, "cop", games_base=base, max_retries=2)

        result = agent.take_turn(gid)
        assert result.success


def test_forfeit_increments_counter() -> None:
    """After max_retries exhausted, consecutive_forfeits increments."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        wrapper = MagicMock()
        # cop at (0,0) — "N" is always illegal (off grid)
        wrapper.get_action.return_value = ("N", "going north")
        agent = _make_agent(wrapper, "cop", games_base=base, max_retries=0, max_forfeits=5)

        agent.take_turn(gid)
        assert agent._consecutive_forfeits == 1


def test_technical_loss_error_raised() -> None:
    """Exceeding max_consecutive_forfeits raises TechnicalLossError."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        wrapper = MagicMock()
        wrapper.get_action.return_value = ("N", "off-grid")
        agent = _make_agent(wrapper, "cop", games_base=base, max_retries=0, max_forfeits=2)

        agent.take_turn(gid)  # forfeit 1
        with pytest.raises(TechnicalLossError):
            agent.take_turn(gid)  # forfeit 2 → TechnicalLossError


def test_set_opponent_message_stored() -> None:
    """set_opponent_message persists for the next render call."""
    wrapper = MagicMock()
    agent = _make_agent(wrapper, "cop")
    agent.set_opponent_message("Hello!")
    assert agent._last_opponent_message == "Hello!"


def test_invalid_actor_raises_value_error() -> None:
    """Agent raises ValueError for unknown actor string."""
    wrapper = MagicMock()
    with pytest.raises(ValueError):
        Agent(wrapper, "unknown")
