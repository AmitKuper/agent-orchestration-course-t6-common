"""Unit tests for game.wrappers.mcp_report_tool."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from game.wrappers.mcp_report_tool import _build_body, register_report_tool


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_report_tool with a capturing mock; return collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def tool_factory() -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = tool_factory
    register_report_tool(mcp)
    return registry


def test_registers_send_game_summary() -> None:
    """register_report_tool adds send_game_summary to the MCP server."""
    registry = _register(MagicMock())
    assert "send_game_summary" in registry


def test_send_game_summary_disabled_when_gmail_off() -> None:
    """send_game_summary returns sent=False when Gmail plugin is disabled."""
    registry = _register(MagicMock())
    with patch("game.gmail.gmail_plugin.os.environ.get", return_value="false"):
        result = json.loads(registry["send_game_summary"](
            series_id="s001", winner_name="Amit",
            cop_total=120, thief_total=30, num_sub_games=6,
        ))
    assert result.get("sent") is False


def test_send_game_summary_sends_when_enabled() -> None:
    """send_game_summary calls send_email and returns sent=True when Gmail is on."""
    registry = _register(MagicMock())
    env = {
        "GMAIL_ENABLED": "true",
        "GMAIL_RECIPIENT": "test@example.com",
        "PLAYER_NAME": "Amit",
    }
    with patch("game.gmail.gmail_plugin.os.environ.get", side_effect=env.get), \
         patch("game.wrappers.mcp_report_tool.os.environ.get", side_effect=env.get), \
         patch("game.gmail.sender.send_email") as mock_send:
        result = json.loads(registry["send_game_summary"](
            series_id="s001", winner_name="Amit",
            cop_total=120, thief_total=30, num_sub_games=6,
        ))
    mock_send.assert_called_once()
    assert result.get("sent") is True
    assert result.get("from") == "Amit"


def test_send_game_summary_subject_names_both_players() -> None:
    """send_game_summary subject reads 'Game Result <local> vs <opponent>'."""
    registry = _register(MagicMock())
    env = {
        "GMAIL_ENABLED": "true",
        "GMAIL_RECIPIENT": "test@example.com",
        "PLAYER_NAME": "Amit",
    }
    with patch("game.gmail.gmail_plugin.os.environ.get", side_effect=env.get), \
         patch("game.wrappers.mcp_report_tool.os.environ.get", side_effect=env.get), \
         patch("game.gmail.sender.send_email") as mock_send:
        registry["send_game_summary"](
            series_id="s001", winner_name="Amit",
            cop_total=120, thief_total=30, num_sub_games=6,
            opponent_name="ZeroOne-01",
        )
    subject = mock_send.call_args.args[1]
    assert subject == "Game Result Amit vs ZeroOne-01 | Series s001"


def test_send_game_summary_returns_error_on_exception() -> None:
    """send_game_summary returns JSON error dict when send_email raises."""
    registry = _register(MagicMock())
    env = {"GMAIL_ENABLED": "true", "GMAIL_RECIPIENT": "test@example.com"}
    with patch("game.gmail.gmail_plugin.os.environ.get", side_effect=env.get), \
         patch("game.gmail.sender.send_email", side_effect=RuntimeError("auth fail")):
        result = json.loads(registry["send_game_summary"](
            series_id="s001", winner_name="Amit",
            cop_total=0, thief_total=0, num_sub_games=1,
        ))
    assert "error" in result


def test_build_body_contains_winner_name() -> None:
    """_build_body includes the winner name prominently."""
    body = _build_body("Ron", "s007", "Amit", 120, 30, 6)
    assert "Amit" in body
    assert "WINNER" in body


def test_build_body_contains_scores() -> None:
    """_build_body includes cop and thief totals."""
    body = _build_body("Ron", "s007", "Amit", 120, 30, 6)
    assert "120" in body
    assert "30" in body


def test_build_body_contains_player_name() -> None:
    """_build_body identifies the reporting player."""
    body = _build_body("Ron", "s007", "Amit", 120, 30, 6)
    assert "Ron" in body


def test_build_body_names_both_teams() -> None:
    """_build_body appends the playing teams line after the footer."""
    body = _build_body("Ron", "s007", "Amit", 120, 30, 6, "", "ZeroOne-01")
    assert "The playing teams are: Ron vs ZeroOne-01" in body
    footer = "Sent automatically by the Cop & Thief MCP game engine."
    assert body.index(footer) < body.index("The playing teams are:")


def test_build_body_lists_players_at_end() -> None:
    """_build_body adds a Players line with both teams' members at the very end."""
    body = _build_body(
        "vibecode", "s007", "vibecode", 10, 20, 2, "", "ZeroOne-01",
        "Amit Kuperminz & Ron Marom", "Lahav Tsur & Evyatar B.",
    )
    expected = "Players: Amit Kuperminz & Ron Marom vs Lahav Tsur & Evyatar B."
    assert body.rstrip().endswith(expected)
    assert body.index("The playing teams are:") < body.index("Players:")
