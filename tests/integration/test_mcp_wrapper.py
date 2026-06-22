"""Integration tests: FastMCP tool functions exercise the full stack.

We call the MCP tool functions directly (bypassing the MCP protocol layer)
to verify they return valid JSON and produce the correct game outcomes.

These tests are skipped when fastmcp is not importable from the active
Python interpreter (e.g. when running via uv PYTHONPATH injection without
the project venv as sys.executable).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not available in this Python environment")


def _play(base: Path, *moves: tuple[str, str]) -> list[dict]:
    """Create a 3x3 game and play the given (actor, action) sequence."""
    from game.sdk import sdk

    info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
    gid = info["game_id"]
    results = []
    for actor, action in moves:
        r = sdk.submit_action(gid, actor, action, games_base=base)
        results.append(json.loads(r.to_json()))
    return results


def test_mcp_new_game_tool() -> None:
    """MCP new_game tool returns JSON with game_id."""
    with patch("game.wrappers.mcp_tools.sdk_new_game") as mock:
        mock.return_value = {"game_id": "deadbeef"}
        from game.wrappers import mcp_tools
        result = json.loads(mcp_tools.new_game(5, 5, 0, 0, 4, 4))
        assert result["game_id"] == "deadbeef"


def test_mcp_submit_action_tool_valid() -> None:
    """MCP submit_action tool returns success JSON for a valid move."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk
        from game.wrappers import mcp_tools

        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        # Patch sdk inside mcp_tools to use our temp base
        with patch("game.wrappers.mcp_tools.sdk_submit_action",
                   side_effect=lambda g, a, act: sdk.submit_action(g, a, act, games_base=base)):
            raw = mcp_tools.submit_action(gid, "cop", "E")
            data = json.loads(raw)
            assert data["success"] is True
            assert data["game_over"] is False


def test_mcp_get_state_tool() -> None:
    """MCP get_state tool returns a valid ObservationState JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk
        from game.wrappers import mcp_tools

        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        with patch("game.wrappers.mcp_tools.sdk_get_state",
                   side_effect=lambda g, a: sdk.get_state(g, a, games_base=base)):
            raw = mcp_tools.get_state(gid, "cop")
            data = json.loads(raw)
            assert data["actor"] == "cop"
            assert "legal_moves" in data
            assert data["barriers_remaining"] == 5


def test_mcp_game_hash_tool() -> None:
    """MCP game_hash tool returns an 8-char hex string."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk
        from game.wrappers import mcp_tools

        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        with patch("game.wrappers.mcp_tools.sdk_hash",
                   side_effect=lambda g: sdk.state_hash(g, games_base=base)):
            raw = mcp_tools.game_hash(gid)
            data = json.loads(raw)
            assert "hash" in data
            assert len(data["hash"]) == 8
            int(data["hash"], 16)  # valid hex


def test_mcp_submit_returns_error_json_on_bad_game() -> None:
    """MCP submit_action returns JSON error dict for unknown game_id."""
    from game.wrappers import mcp_tools

    with patch("game.wrappers.mcp_tools.sdk_submit_action",
               side_effect=FileNotFoundError("no game")):
        raw = mcp_tools.submit_action("nope", "cop", "E")
        data = json.loads(raw)
        assert "error" in data


def test_mcp_full_game_sequence() -> None:
    """MCP: simulate a full game (new → submit × 2 → capture) via tool patches."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk
        from game.wrappers import mcp_tools

        # Create the game through the real SDK (simulating the new_game call)
        info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
        gid = info["game_id"]

        with patch("game.wrappers.mcp_tools.sdk_submit_action",
                   side_effect=lambda g, a, act: sdk.submit_action(g, a, act, games_base=base)):
            r1 = json.loads(mcp_tools.submit_action(gid, "cop", "SE"))
            assert r1["success"] is True

            r2 = json.loads(mcp_tools.submit_action(gid, "thief", "NW"))
            assert r2["game_over"] is True
            assert r2["winner"] == "cop"
            assert r2["win_reason"] == "capture"
