"""Unit tests for actor.random_actor and actor.actor_wrapper."""

from unittest.mock import MagicMock

from actor.actor_wrapper import ActorWrapper
from actor.random_actor import RandomActorBackend
from game.state import ActionResult, ObservationState


def _obs(**kwargs: object) -> ObservationState:
    """Build a minimal ObservationState."""
    defaults = dict(
        actor="cop", round=1, my_pos=(0, 0), opponent_pos=(4, 4),
        barriers=[], legal_moves=["E", "S", "SE"], barriers_remaining=3,
    )
    return ObservationState(**{**defaults, **kwargs})


# ── RandomActorBackend ────────────────────────────────────────────────────────

def test_random_actor_returns_legal_move() -> None:
    """get_action always returns a move from legal_moves."""
    obs = _obs(legal_moves=["N", "E", "S"])
    backend = RandomActorBackend(seed=42)
    action = backend.get_action(obs)
    assert action in obs.legal_moves


def test_random_actor_deterministic_with_seed() -> None:
    """Same seed → same sequence."""
    obs = _obs(legal_moves=["N", "E", "S", "W"])
    a1 = RandomActorBackend(seed=7).get_action(obs)
    a2 = RandomActorBackend(seed=7).get_action(obs)
    assert a1 == a2


def test_random_actor_on_result_is_noop() -> None:
    """on_result does not raise (default no-op inherited from BaseActor)."""
    obs = _obs()
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    RandomActorBackend(seed=1).on_result(obs, "E", result)  # should not raise


# ── ActorWrapper ──────────────────────────────────────────────────────────────

def test_wrapper_returns_action_and_message() -> None:
    """get_action returns (action_str, nl_message) pair."""
    backend = RandomActorBackend(seed=0)
    wrapper = ActorWrapper(backend, role="cop")
    obs = _obs(legal_moves=["E"])
    action, message = wrapper.get_action(obs)
    assert action == "E"
    assert isinstance(message, str)
    assert len(message) > 0


def test_wrapper_message_contains_destination_for_move() -> None:
    """Move message includes destination coordinates."""
    backend = MagicMock()
    backend.get_action.return_value = "E"
    wrapper = ActorWrapper(backend, role="cop")
    obs = _obs(my_pos=(1, 2), legal_moves=["E"])
    _, message = wrapper.get_action(obs)
    assert "[2, 2]" in message  # E moves x+1


def test_wrapper_barrier_message() -> None:
    """BARRIER action produces a barrier-specific message."""
    backend = MagicMock()
    backend.get_action.return_value = "BARRIER"
    wrapper = ActorWrapper(backend, role="cop")
    obs = _obs(my_pos=(3, 3), legal_moves=["BARRIER"])
    _, message = wrapper.get_action(obs)
    assert "barrier" in message.lower()


def test_wrapper_on_result_delegates_to_backend() -> None:
    """on_result passes through to backend.on_result."""
    backend = MagicMock()
    wrapper = ActorWrapper(backend, role="thief")
    obs = _obs()
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    wrapper.on_result(obs, "N", result)
    backend.on_result.assert_called_once_with(obs, "N", result)
