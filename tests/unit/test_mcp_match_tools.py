"""Unit tests for game.wrappers.mcp_match_tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import MagicMock, patch

from game.wrappers.mcp_match_tools import register_match_tools


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_match_tools with a capturing mock; return collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def tool_factory() -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[fn.__name__] = fn
            return fn
        return decorator

    mcp.tool = tool_factory
    register_match_tools(mcp)
    return registry


def test_registers_get_player_name() -> None:
    """register_match_tools adds get_player_name to the MCP server."""
    registry = _register(MagicMock())
    assert "get_player_name" in registry


def test_get_player_name_reads_env() -> None:
    """get_player_name returns the PLAYER_NAME environment value."""
    registry = _register(MagicMock())
    with patch("game.wrappers.mcp_match_tools.os.environ.get", return_value="ZeroOne-01"):
        result = json.loads(registry["get_player_name"]())
    assert result == {"player_name": "ZeroOne-01"}
