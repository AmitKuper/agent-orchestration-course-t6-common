"""Unit tests for game.wrappers.mcp_prompts — cop_rules and thief_rules prompts."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from game.wrappers.mcp_prompts import register_prompts


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_prompts with a capturing mock; return the collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def prompt_factory() -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[fn.__name__] = fn
            return fn
        return decorator

    mcp.prompt = prompt_factory
    register_prompts(mcp)
    return registry


def test_register_prompts_registers_cop_and_thief() -> None:
    """register_prompts adds cop_rules and thief_rules to the MCP server."""
    registry = _register(MagicMock())
    assert "cop_rules" in registry
    assert "thief_rules" in registry


def test_cop_rules_contains_cop_and_barrier() -> None:
    """cop_rules prompt mentions COP and BARRIER."""
    registry = _register(MagicMock())
    text = registry["cop_rules"]()
    assert "COP" in text
    assert "BARRIER" in text


def test_thief_rules_contains_thief() -> None:
    """thief_rules prompt mentions THIEF."""
    registry = _register(MagicMock())
    assert "THIEF" in registry["thief_rules"]()


def test_cop_rules_includes_game_id_header() -> None:
    """cop_rules includes the game_id in the text when provided."""
    registry = _register(MagicMock())
    assert "match0042" in registry["cop_rules"](game_id="match0042")


def test_thief_rules_no_barrier_placement() -> None:
    """thief_rules states the thief cannot place barriers."""
    registry = _register(MagicMock())
    text = registry["thief_rules"]()
    assert "cannot" in text.lower()


def test_cop_rules_returns_string() -> None:
    """cop_rules returns a non-empty string."""
    registry = _register(MagicMock())
    result = registry["cop_rules"]()
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("role_fn,expected", [
    ("cop_rules", "COP"),
    ("thief_rules", "THIEF"),
])
def test_rules_contain_role_keyword(role_fn: str, expected: str) -> None:
    """Each rules prompt mentions the corresponding role keyword."""
    registry = _register(MagicMock())
    assert expected in registry[role_fn]()
