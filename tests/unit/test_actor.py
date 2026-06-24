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


class _ConcreteWrapper(ActorWrapper):
    """Minimal concrete ActorWrapper for testing — returns a fixed message."""

    def _render_message(self, obs: ObservationState, action: str) -> str:
        """Return a fixed test message."""
        return f"test:{action}"


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
    RandomActorBackend(seed=1).on_result(obs, "E", result)


# ── ActorWrapper ──────────────────────────────────────────────────────────────

def test_wrapper_returns_action_and_message() -> None:
    """get_action returns (action_str, nl_message) pair."""
    wrapper = _ConcreteWrapper(RandomActorBackend(seed=0), role="cop")
    action, message = wrapper.get_action(_obs(legal_moves=["E"]))
    assert action == "E"
    assert message == "test:E"


def test_wrapper_render_message_must_be_overridden() -> None:
    """Base ActorWrapper._render_message raises NotImplementedError."""
    backend = MagicMock()
    backend.get_action.return_value = "E"
    wrapper = ActorWrapper(backend, role="cop")
    try:
        wrapper.get_action(_obs(legal_moves=["E"]))
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


def test_wrapper_on_result_delegates_to_backend() -> None:
    """on_result passes through to backend.on_result."""
    backend = MagicMock()
    wrapper = _ConcreteWrapper(backend, role="thief")
    obs = _obs()
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    wrapper.on_result(obs, "N", result)
    backend.on_result.assert_called_once_with(obs, "N", result)
