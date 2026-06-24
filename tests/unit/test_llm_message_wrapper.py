"""Unit tests for actor.llm_message_wrapper — LLMMessageWrapper and factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actor.llm_message_wrapper import LLMMessageWrapper, create_llm_message_wrapper
from game.state import ActionResult, ObservationState


def _obs() -> ObservationState:
    """Build a minimal ObservationState."""
    return ObservationState(
        actor="cop", round=1, my_pos=(0, 0), opponent_pos=(4, 4),
        barriers=[], legal_moves=["E"], barriers_remaining=5,
    )


def _mock_backend(action: str = "E") -> MagicMock:
    """Return a mock BaseActor that always returns the given action."""
    b = MagicMock()
    b.get_action.return_value = action
    return b


def _mock_gk(message: str = "ok") -> MagicMock:
    """Return a mock Gatekeeper that returns message on every call."""
    gk = MagicMock()
    gk.call.return_value = message
    return gk


def test_wrapper_uses_backend_for_action() -> None:
    """Action comes from the backend, not the LLM."""
    wrapper = LLMMessageWrapper(_mock_backend("E"), _mock_gk(), role="cop")
    action, _ = wrapper.get_action(_obs())
    assert action == "E"


def test_wrapper_uses_llm_for_message() -> None:
    """NL message comes from the LLM gatekeeper, not a template."""
    wrapper = LLMMessageWrapper(_mock_backend(), _mock_gk("Cutting off the thief."), role="cop")
    _, message = wrapper.get_action(_obs())
    assert message == "Cutting off the thief."


def test_wrapper_strips_whitespace_from_llm_response() -> None:
    """Trailing whitespace in the LLM response is stripped."""
    wrapper = LLMMessageWrapper(_mock_backend(), _mock_gk("  Moving east.  \n"), role="cop")
    _, message = wrapper.get_action(_obs())
    assert message == "Moving east."


def test_wrapper_cop_system_prompt_contains_cop() -> None:
    """Cop role passes a COP-specific system prompt to the gatekeeper."""
    gk = _mock_gk()
    wrapper = LLMMessageWrapper(_mock_backend(), gk, role="cop")
    wrapper.get_action(_obs())
    _, kwargs = gk.call.call_args
    assert "COP" in kwargs.get("system", "")


def test_wrapper_thief_system_prompt_contains_thief() -> None:
    """Thief role passes a THIEF-specific system prompt to the gatekeeper."""
    gk = _mock_gk()
    wrapper = LLMMessageWrapper(_mock_backend(), gk, role="thief")
    wrapper.get_action(_obs())
    _, kwargs = gk.call.call_args
    assert "THIEF" in kwargs.get("system", "")


def test_wrapper_prompt_includes_action() -> None:
    """The LLM prompt contains the chosen action string."""
    gk = _mock_gk()
    wrapper = LLMMessageWrapper(_mock_backend("NW"), gk, role="thief")
    wrapper.get_action(_obs())
    prompt_text = gk.call.call_args[0][0][0]["content"]
    assert "NW" in prompt_text


def test_wrapper_on_result_delegates_to_backend() -> None:
    """on_result is forwarded to the backend."""
    backend = _mock_backend()
    wrapper = LLMMessageWrapper(backend, _mock_gk(), role="cop")
    obs = _obs()
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    wrapper.on_result(obs, "E", result)
    backend.on_result.assert_called_once_with(obs, "E", result)


def test_create_llm_message_wrapper_returns_instance() -> None:
    """Factory returns an LLMMessageWrapper."""
    with patch("game.shared.gatekeeper.anthropic.Anthropic"), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        wrapper = create_llm_message_wrapper(_mock_backend(), "cop")
    assert isinstance(wrapper, LLMMessageWrapper)
