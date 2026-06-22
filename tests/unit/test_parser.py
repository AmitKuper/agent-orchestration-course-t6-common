"""Unit tests for game.agent.parser."""

import pytest

from game.agent.parser import ParseError, parse_response


def test_extracts_action_from_explicit_line() -> None:
    """Action: NE line yields 'NE'."""
    text = "I'm moving northeast.\nAction: NE"
    action, msg = parse_response(text, ["N", "NE", "E"])
    assert action == "NE"


def test_message_is_text_before_action_line() -> None:
    """Everything before the Action: line becomes the message."""
    text = "Going north to chase.\nAction: N"
    _, msg = parse_response(text, ["N", "E"])
    assert "Going north" in msg


def test_action_case_insensitive_label() -> None:
    """'action: ne' (lower-case label) is still parsed."""
    text = "action: NE"
    action, _ = parse_response(text, ["NE"])
    assert action == "NE"


def test_illegal_token_raises_parse_error() -> None:
    """Token not in legal_moves raises ParseError."""
    text = "Action: Z"
    with pytest.raises(ParseError, match="not in legal moves"):
        parse_response(text, ["N", "E"])


def test_fallback_finds_standalone_token() -> None:
    """When no Action: line exists, a standalone legal token is used."""
    text = "I'll go NE this turn."
    action, _ = parse_response(text, ["N", "NE"])
    assert action == "NE"


def test_no_action_raises_parse_error() -> None:
    """Completely unparseable response raises ParseError."""
    with pytest.raises(ParseError):
        parse_response("No valid move here at all.", ["N", "E"])


def test_barrier_action_parsed() -> None:
    """BARRIER keyword is extracted correctly."""
    text = "Placing barrier.\nAction: BARRIER"
    action, _ = parse_response(text, ["N", "BARRIER"])
    assert action == "BARRIER"


def test_empty_message_falls_back_to_full_text() -> None:
    """When action line is first, message falls back to full stripped text."""
    text = "Action: E"
    action, msg = parse_response(text, ["E"])
    assert action == "E"
    assert msg  # non-empty
