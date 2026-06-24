"""Unit tests for actor.llm_actor — LLMActorBackend, LLMActorWrapper, create_llm_wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from actor.llm_actor import LLMActorBackend, LLMActorWrapper, create_llm_wrapper
from game.agent.parser import ParseError
from game.state import ObservationState


def _obs(**kwargs: object) -> ObservationState:
    """Build a minimal ObservationState for testing."""
    defaults = dict(
        actor="cop", round=1, my_pos=(0, 0), opponent_pos=(4, 4),
        barriers=[], legal_moves=["E", "S", "SE"], barriers_remaining=5,
    )
    return ObservationState(**{**defaults, **kwargs})


def _mock_gk(*responses: str) -> MagicMock:
    """Return a mock Gatekeeper with sequential call responses."""
    gk = MagicMock()
    gk.call.side_effect = list(responses)
    return gk


def test_llm_backend_returns_legal_action() -> None:
    """get_action parses the LLM response and returns a legal action."""
    backend = LLMActorBackend(_mock_gk("Heading east.\nAction: E"))
    assert backend.get_action(_obs()) == "E"


def test_llm_backend_stores_nl_message() -> None:
    """get_action stores the NL message portion in last_message."""
    backend = LLMActorBackend(_mock_gk("Closing in.\nAction: SE"))
    backend.get_action(_obs())
    assert "Closing" in backend.last_message


def test_llm_backend_retries_on_parse_error() -> None:
    """On ParseError the backend sends a clarification and retries."""
    gk = _mock_gk(
        "I have no idea.",           # first response: unparseable
        "Moving east.\nAction: E",   # second response: valid
    )
    backend = LLMActorBackend(gk, max_retries=1)
    action = backend.get_action(_obs())
    assert action == "E"
    assert gk.call.call_count == 2


def test_llm_backend_clarification_appended_to_messages() -> None:
    """The clarification request is appended to the conversation, not a fresh prompt."""
    gk = _mock_gk("bad response", "Going south.\nAction: S")
    backend = LLMActorBackend(gk, max_retries=1)
    backend.get_action(_obs())

    second_call_messages = gk.call.call_args_list[1][0][0]
    # conversation should have: initial user, bad assistant, clarification user
    assert len(second_call_messages) == 3
    assert second_call_messages[1]["role"] == "assistant"
    assert second_call_messages[2]["role"] == "user"
    assert "Action:" in second_call_messages[2]["content"]


def test_llm_backend_raises_after_all_retries_exhausted() -> None:
    """ParseError is raised when all retry attempts fail — no silent fallback."""
    gk = _mock_gk("bad", "also bad", "still bad")
    backend = LLMActorBackend(gk, max_retries=2)
    with pytest.raises(ParseError):
        backend.get_action(_obs())
    assert gk.call.call_count == 3


def test_llm_backend_illegal_action_raises() -> None:
    """ParseError raised when LLM returns an action not in legal_moves after retries."""
    gk = _mock_gk("Action: N", "Action: N", "Action: N")  # N not legal
    backend = LLMActorBackend(gk, max_retries=2)
    with pytest.raises(ParseError):
        backend.get_action(_obs(legal_moves=["E", "S"]))


def test_llm_backend_passes_system_prompt() -> None:
    """The system prompt is forwarded to Gatekeeper.call."""
    gk = _mock_gk("Moving east.\nAction: E")
    backend = LLMActorBackend(gk, system_prompt="You are the cop.")
    backend.get_action(_obs())
    _, kwargs = gk.call.call_args
    assert kwargs.get("system") == "You are the cop."


def test_llm_wrapper_get_action_returns_tuple() -> None:
    """LLMActorWrapper.get_action returns (action, message) tuple."""
    gk = _mock_gk("Moving south.\nAction: S")
    wrapper = LLMActorWrapper(gk, role="cop")
    action, message = wrapper.get_action(_obs())
    assert action == "S"
    assert "Moving south" in message


def test_llm_wrapper_message_from_llm_not_template() -> None:
    """NL message comes from the LLM, not the default template string."""
    gk = _mock_gk("Sneaking away quietly.\nAction: E")
    wrapper = LLMActorWrapper(gk, role="thief")
    _, message = wrapper.get_action(_obs(actor="thief", barriers_remaining=None))
    assert "Sneaking" in message
    assert "Moving" not in message


def test_llm_wrapper_cop_system_prompt_contains_barrier() -> None:
    """Cop role uses a system prompt that mentions BARRIER."""
    gk = _mock_gk("Going east.\nAction: E")
    wrapper = LLMActorWrapper(gk, role="cop")
    wrapper.get_action(_obs())
    system_arg = gk.call.call_args[1].get("system", "")
    assert "BARRIER" in system_arg


def test_llm_wrapper_thief_system_prompt() -> None:
    """Thief role uses a system prompt that mentions THIEF."""
    gk = _mock_gk("Going east.\nAction: E")
    wrapper = LLMActorWrapper(gk, role="thief")
    wrapper.get_action(_obs(actor="thief", barriers_remaining=None))
    system_arg = gk.call.call_args[1].get("system", "")
    assert "THIEF" in system_arg


def test_llm_wrapper_propagates_parse_error() -> None:
    """ParseError from backend propagates out of LLMActorWrapper.get_action."""
    gk = _mock_gk("no action here", "still nothing", "nothing")
    wrapper = LLMActorWrapper(gk, role="cop")
    with pytest.raises(ParseError):
        wrapper.get_action(_obs())


def test_create_llm_wrapper_returns_llm_actor_wrapper() -> None:
    """create_llm_wrapper returns an LLMActorWrapper instance."""
    with patch("game.shared.gatekeeper.anthropic.Anthropic"), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        wrapper = create_llm_wrapper("cop")
    assert isinstance(wrapper, LLMActorWrapper)


def test_create_llm_wrapper_respects_llm_model_env() -> None:
    """create_llm_wrapper passes LLM_MODEL env var to the Gatekeeper."""
    env = {"ANTHROPIC_API_KEY": "k", "LLM_MODEL": "claude-haiku-4-5-20251001"}
    with patch("game.shared.gatekeeper.anthropic.Anthropic"), \
         patch.dict("os.environ", env):
        wrapper = create_llm_wrapper("thief")
    assert wrapper._backend._gk.model == "claude-haiku-4-5-20251001"
