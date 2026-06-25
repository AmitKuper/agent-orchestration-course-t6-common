"""Unit tests for game.wrappers.mcp_sync_tools."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from game.wrappers.mcp_sync_tools import register_sync_tools


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_sync_tools with a capturing mock; return collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def tool_factory() -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = tool_factory
    register_sync_tools(mcp)
    return registry


def test_register_sync_tools_registers_all_three() -> None:
    """register_sync_tools adds receive_action, get_hash, propose_match_tool."""
    registry = _register(MagicMock())
    assert "receive_action" in registry
    assert "get_hash" in registry
    assert "propose_match_tool" in registry


def test_get_hash_returns_error_for_missing_game() -> None:
    """get_hash returns JSON error when game does not exist."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        with patch("game.wrappers.mcp_state.server_state", {"games_base": Path(tmp)}):
            result = json.loads(registry["get_hash"](game_id="no_such_game"))
    assert "error" in result


def test_get_hash_returns_hash_for_live_game() -> None:
    """get_hash returns an 8-char hex string for an active game."""
    from game.sdk.sdk import new_game as sdk_new_game

    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sdk_new_game(grid_size=(5, 5), cop_pos=(0, 0), thief_pos=(4, 4),
                     seed=1, games_base=base)
        game_id = next(p.name for p in base.iterdir())
        with patch("game.wrappers.mcp_state.server_state", {"games_base": base}):
            result = json.loads(registry["get_hash"](game_id=game_id))
    assert "hash" in result
    assert len(result["hash"]) == 8


def test_receive_action_returns_error_for_missing_game() -> None:
    """receive_action returns JSON error when game does not exist."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        with patch("game.wrappers.mcp_state.server_state", {"games_base": Path(tmp)}):
            result = json.loads(
                registry["receive_action"](game_id="no_game", actor="cop", action="E")
            )
    assert "error" in result


def test_receive_action_applies_action_to_live_game() -> None:
    """receive_action applies a legal action and returns success."""
    from game.sdk.sdk import new_game as sdk_new_game

    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sdk_new_game(grid_size=(5, 5), cop_pos=(0, 0), thief_pos=(4, 4),
                     seed=1, games_base=base)
        game_id = next(p.name for p in base.iterdir())
        with patch("game.wrappers.mcp_state.server_state", {"games_base": base}):
            result = json.loads(
                registry["receive_action"](game_id=game_id, actor="cop", action="E")
            )
    assert result.get("success") is True


def test_propose_match_tool_creates_game() -> None:
    """propose_match_tool creates a game and returns accepted=True."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        with patch("game.wrappers.mcp_state.server_state",
                   {"games_base": base, "matches": {}}):
            result = json.loads(registry["propose_match_tool"](
                game_id="test_match",
                seed=42,
                cop_pos=[0, 0],
                thief_pos=[4, 4],
                grid_size=[5, 5],
                my_role="cop",
            ))
    assert result.get("accepted") is True
    assert result.get("game_id") == "test_match"


def test_propose_match_tool_returns_error_on_bad_input() -> None:
    """propose_match_tool returns JSON error for invalid positions."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        with patch("game.wrappers.mcp_state.server_state",
                   {"games_base": base, "matches": {}}):
            result = json.loads(registry["propose_match_tool"](
                game_id="bad_match",
                seed=1,
                cop_pos=[0, 0],
                thief_pos=[0, 0],
                grid_size=[5, 5],
                my_role="thief",
            ))
    assert "error" in result
