"""Unit tests for game.wrappers.mcp_agent_tools — GAME_TOOLS and registered tools."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from game.wrappers.mcp_agent_tools import GAME_TOOLS, register_agent_tools


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_agent_tools with a capturing mock; return the collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def tool_factory() -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = tool_factory
    register_agent_tools(mcp)
    return registry


def test_game_tools_contains_get_state_and_take_action() -> None:
    """GAME_TOOLS list includes get_state and take_action definitions."""
    names = {t["name"] for t in GAME_TOOLS}
    assert "get_state" in names
    assert "take_action" in names


def test_game_tools_have_required_fields() -> None:
    """Each tool in GAME_TOOLS has name, description, and input_schema."""
    for tool in GAME_TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool


def test_register_agent_tools_registers_get_state_and_take_action() -> None:
    """register_agent_tools adds get_state and take_action to the MCP server."""
    registry = _register(MagicMock())
    assert "get_state" in registry
    assert "take_action" in registry


def test_get_state_returns_error_for_missing_game() -> None:
    """get_state returns JSON error when game does not exist."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        with patch("game.wrappers.mcp_state.server_state", {"games_base": Path(tmp)}):
            result = json.loads(registry["get_state"](game_id="no_game", actor="cop"))
    assert "error" in result


def test_get_state_returns_observation_for_live_game() -> None:
    """get_state returns ObservationState JSON for an active game."""
    from game.sdk.sdk import new_game as sdk_new_game

    registry = _register(MagicMock())

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sdk_new_game(grid_size=(5, 5), cop_pos=(0, 0), thief_pos=(4, 4),
                     seed=1, games_base=base)
        game_id = next(p.name for p in base.iterdir())
        with patch("game.wrappers.mcp_state.server_state", {"games_base": base}):
            result = json.loads(registry["get_state"](game_id=game_id, actor="cop"))
    assert "actor" in result
    assert result["actor"] == "cop"


def test_take_action_returns_error_for_missing_game() -> None:
    """take_action returns JSON error when game does not exist."""
    import asyncio
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        with patch("game.wrappers.mcp_state.server_state", {"games_base": Path(tmp)}):
            result = json.loads(
                asyncio.run(registry["take_action"](game_id="no_game", actor="cop", action="E"))
            )
    assert "error" in result


def test_game_tools_take_action_requires_action() -> None:
    """take_action tool definition lists 'action' as a required field."""
    take_action = next(t for t in GAME_TOOLS if t["name"] == "take_action")
    assert "action" in take_action["input_schema"]["required"]


def test_game_tools_contains_get_actor_action() -> None:
    """GAME_TOOLS includes get_actor_action definition."""
    names = {t["name"] for t in GAME_TOOLS}
    assert "get_actor_action" in names


def test_register_agent_tools_registers_get_actor_action() -> None:
    """register_agent_tools adds get_actor_action to the MCP server."""
    registry = _register(MagicMock())
    assert "get_actor_action" in registry


def test_get_actor_action_returns_error_for_missing_game() -> None:
    """get_actor_action returns JSON error when game does not exist."""
    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        with patch("game.wrappers.mcp_state.server_state", {"games_base": Path(tmp)}):
            result = json.loads(registry["get_actor_action"](game_id="no_game", actor="cop"))
    assert "error" in result


def test_get_actor_action_returns_action_for_live_game() -> None:
    """get_actor_action returns a legal action for an active game."""
    from game.sdk.sdk import new_game as sdk_new_game

    registry = _register(MagicMock())
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sdk_new_game(grid_size=(5, 5), cop_pos=(0, 0), thief_pos=(4, 4),
                     seed=1, games_base=base)
        game_id = next(p.name for p in base.iterdir())
        with patch("game.wrappers.mcp_state.server_state", {"games_base": base}):
            result = json.loads(registry["get_actor_action"](game_id=game_id, actor="thief"))
    assert "action" in result
    assert "legal_moves" in result
    assert result["action"] in result["legal_moves"]
