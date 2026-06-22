"""Unit tests for game.agent.renderer."""

from game.agent.renderer import render_observation
from game.state import ObservationState


def _obs(**kwargs: object) -> ObservationState:
    """Build a minimal ObservationState with sane defaults."""
    defaults = dict(
        actor="cop", round=1, my_pos=(1, 1), opponent_pos=None,
        barriers=[], legal_moves=["N", "E", "S", "W"], barriers_remaining=3,
    )
    return ObservationState(**{**defaults, **kwargs})


def test_render_includes_round_role_position() -> None:
    """Rendered prompt contains round, role label, and position."""
    text = render_observation(_obs(actor="cop", round=3, my_pos=(2, 4)))
    assert "Round 3" in text
    assert "COP" in text
    assert "[2, 4]" in text


def test_render_shows_opponent_when_visible() -> None:
    """Opponent position appears when visible."""
    text = render_observation(_obs(opponent_pos=(3, 3)))
    assert "[3, 3]" in text
    assert "visible" in text


def test_render_hides_opponent_when_not_visible() -> None:
    """Opponent position is marked unknown when outside view radius."""
    text = render_observation(_obs(opponent_pos=None))
    assert "unknown" in text


def test_render_includes_barriers() -> None:
    """Barrier positions appear in the prompt."""
    text = render_observation(_obs(barriers=[(1, 0), (2, 3)]))
    assert "[1, 0]" in text


def test_render_no_barriers_message() -> None:
    """Renders 'none' when there are no barriers."""
    text = render_observation(_obs(barriers=[]))
    assert "none" in text.lower()


def test_render_includes_legal_moves() -> None:
    """Legal moves appear in the prompt."""
    text = render_observation(_obs(legal_moves=["N", "BARRIER"]))
    assert "N" in text
    assert "BARRIER" in text


def test_render_includes_opponent_message() -> None:
    """Opponent's last message appears in the prompt."""
    text = render_observation(_obs(), last_opponent_message="I'm heading north!")
    assert "I'm heading north!" in text


def test_render_omits_opponent_message_when_none() -> None:
    """Opponent's last message section absent when not provided."""
    text = render_observation(_obs(), last_opponent_message=None)
    assert "Opponent's last message" not in text


def test_render_includes_action_instruction() -> None:
    """Prompt always ends with the Action: instruction."""
    text = render_observation(_obs())
    assert "Action:" in text


def test_render_thief_role_label() -> None:
    """Thief role is rendered as THIEF."""
    text = render_observation(_obs(actor="thief"))
    assert "THIEF" in text
