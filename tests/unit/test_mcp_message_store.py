"""Unit tests for the in-memory MCP message store."""

from game.wrappers.mcp_message_store import (
    clear_game,
    get_opponent_message,
    record_message,
)


def test_record_and_retrieve_opponent_message() -> None:
    """Cop's message is returned when the thief queries its opponent."""
    record_message("g1", "cop", "Moving north to cut off escape")
    assert get_opponent_message("g1", "thief") == "Moving north to cut off escape"


def test_thief_message_retrieved_by_cop() -> None:
    """Thief's message is returned when the cop queries its opponent."""
    record_message("g2", "thief", "Heading southeast, you'll never catch me")
    assert get_opponent_message("g2", "cop") == "Heading southeast, you'll never catch me"


def test_own_message_not_returned() -> None:
    """An actor does not see its own message as the opponent message."""
    record_message("g3", "cop", "Moving south")
    assert get_opponent_message("g3", "cop") is None


def test_empty_message_not_recorded() -> None:
    """Empty string messages are silently ignored."""
    record_message("g4", "cop", "")
    assert get_opponent_message("g4", "thief") is None


def test_latest_message_overwrites_previous() -> None:
    """Recording a second message for the same actor overwrites the first."""
    record_message("g5", "thief", "first")
    record_message("g5", "thief", "second")
    assert get_opponent_message("g5", "cop") == "second"


def test_clear_game_removes_messages() -> None:
    """clear_game purges all stored messages for a game."""
    record_message("g6", "cop", "hello")
    clear_game("g6")
    assert get_opponent_message("g6", "thief") is None


def test_unknown_game_returns_none() -> None:
    """Querying a game with no messages returns None without error."""
    assert get_opponent_message("nonexistent", "cop") is None
