"""Unit tests for game.wrappers.mcp_resources — game://config and game://state resources."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

from game.wrappers.mcp_resources import _GAME_CONFIG, register_resources


def _register(mcp: MagicMock) -> dict[str, Callable[..., str]]:
    """Run register_resources with a capturing mock; return the collected functions."""
    registry: dict[str, Callable[..., str]] = {}

    def resource_factory(uri: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
        def decorator(fn: Callable[..., str]) -> Callable[..., str]:
            registry[uri] = fn
            return fn
        return decorator

    mcp.resource = resource_factory
    register_resources(mcp)
    return registry


def test_register_resources_registers_config() -> None:
    """register_resources adds game://config resource."""
    registry = _register(MagicMock())
    assert "game://config" in registry


def test_register_resources_registers_state_template() -> None:
    """register_resources adds a state URI template resource."""
    registry = _register(MagicMock())
    assert any("state" in k for k in registry)


def test_game_config_is_valid_json() -> None:
    """game://config resource returns parseable JSON."""
    registry = _register(MagicMock())
    data = json.loads(registry["game://config"]())
    assert isinstance(data, dict)


def test_game_config_has_expected_keys() -> None:
    """game://config resource includes grid_size, max_moves, max_barriers."""
    registry = _register(MagicMock())
    data = json.loads(registry["game://config"]())
    for key in ("grid_size", "max_moves", "max_barriers"):
        assert key in data


def test_game_config_matches_internal_constant() -> None:
    """game://config values match _GAME_CONFIG constant."""
    registry = _register(MagicMock())
    data = json.loads(registry["game://config"]())
    assert data["grid_size"] == _GAME_CONFIG["grid_size"]
    assert data["max_moves"] == _GAME_CONFIG["max_moves"]


def test_game_state_returns_error_for_missing_game() -> None:
    """game://{game_id}/state/{actor} returns JSON error when game does not exist."""
    registry = _register(MagicMock())
    state_fn = next(v for k, v in registry.items() if "state" in k)
    result = json.loads(state_fn(game_id="nonexistent", actor="cop"))
    assert "error" in result


def test_game_state_returns_observation_for_valid_game() -> None:
    """game://{game_id}/state/{actor} returns ObservationState for a live game."""
    from game.sdk.sdk import new_game as sdk_new_game

    registry = _register(MagicMock())
    state_fn = next(v for k, v in registry.items() if "state" in k)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sdk_new_game(grid_size=(5, 5), cop_pos=(0, 0), thief_pos=(4, 4),
                     seed=1, games_base=base)
        game_id = next(p.name for p in base.iterdir())
        with patch("game.wrappers.mcp_state.server_state", {"games_base": base}):
            result = json.loads(state_fn(game_id=game_id, actor="cop"))
    assert "actor" in result
