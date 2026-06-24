"""Unit tests for actor.llm_actor — LLMActorBackend, LLMActorWrapper, create_llm_wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from actor.llm_actor import LLMActorBackend, LLMActorWrapper, create_llm_wrapper
from game.state import ObservationState


def _obs(**kwargs: object) -> ObservationState:
    """Build a minimal ObservationState for testing."""
    defaults = dict(
        actor="cop", round=1, my_pos=(0, 0), opponent_pos=(4, 4),
        barriers=[], legal_moves=["E", "S", "SE"], barriers_remaining=5,
    )
    return ObservationState(**{**defaults, **kwargs})


def _mock_gk(response: str = "Moving east to close the gap.\nAction: E") -> MagicMock:
    """Return a mock Gatekeeper that returns a fixed response."""
    gk = MagicMock()
    gk.call.return_value = response
    return gk


def test_llm_backend_returns_legal_action() -> None:
    """get_action parses the LLM response and returns a legal action."""
    backend = LLMActorBackend(_mock_gk("Heading east.\nAction: E"))
    action = backend.get_action(_obs())
    assert action == "E"


def test_llm_backend_stores_nl_message() -> None:
    """get_action stores the NL message portion in last_message."""
    backend = LLMActorBackend(_mock_gk("Closing in.\nAction: SE"))
    backend.get_action(_obs())
    assert "Closing" in backend.last_message


def test_llm_backend_fallback_on_parse_error() -> None:
    """Falls back to first legal move when the LLM response cannot be parsed."""
    backend = LLMActorBackend(_mock_gk("I have no idea what to do here."))
    obs = _obs(legal_moves=["N", "E"])
    action = backend.get_action(obs)
    assert action == "N"


def test_llm_backend_fallback_message_is_raw_response() -> None:
    """On parse failure the raw response is stored as last_message."""
    raw = "Totally unparseable response."
    backend = LLMActorBackend(_mock_gk(raw))
    backend.get_action(_obs(legal_moves=["E"]))
    assert backend.last_message == raw


def test_llm_backend_passes_system_prompt() -> None:
    """The system prompt is forwarded to Gatekeeper.call."""
    gk = _mock_gk()
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
    assert "Moving" not in message  # default template would say "Moving E to position ..."


def test_llm_wrapper_cop_system_prompt() -> None:
    """Cop role uses the COP system prompt (contains 'BARRIER')."""
    gk = _mock_gk()
    wrapper = LLMActorWrapper(gk, role="cop")
    wrapper.get_action(_obs())
    call_args = gk.call.call_args
    system_arg = call_args[1].get("system") or ""
    assert "BARRIER" in system_arg


def test_llm_wrapper_thief_system_prompt() -> None:
    """Thief role uses the THIEF system prompt (does not mention BARRIER as an action)."""
    gk = _mock_gk()
    wrapper = LLMActorWrapper(gk, role="thief")
    wrapper.get_action(_obs(actor="thief", barriers_remaining=None))
    call_args = gk.call.call_args
    system_arg = call_args[1].get("system") or ""
    assert "THIEF" in system_arg


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


def test_llm_backend_illegal_action_falls_back() -> None:
    """If the LLM returns an action not in legal_moves, falls back to first legal move."""
    backend = LLMActorBackend(_mock_gk("Going north.\nAction: N"))
    obs = _obs(legal_moves=["E", "S"])  # N is not legal
    action = backend.get_action(obs)
    assert action == "E"
