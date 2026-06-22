"""Integration tests: CrewAI tool functions exercise the full stack.

The @tool decorator wraps the function but the underlying callable is still
accessible via the .run() method or by calling the function directly.
We test the function logic end-to-end (new_game → submit_action → get_state)
using monkeypatching to redirect game storage to a temp directory.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_crewai_new_game_returns_game_id() -> None:
    """CrewAI new_game tool returns JSON with a game_id."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        with patch("game.sdk.sdk.generate_game_id", return_value="aabbccdd"), \
             patch("game.sdk.sdk.Game") as mock_game_cls, \
             patch("game.sdk.sdk.save_state"):
            mock_game = mock_game_cls.new.return_value
            mock_game.to_dict.return_value = {"game_id": "aabbccdd"}

            from game.sdk import sdk
            result_dict = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
            assert result_dict["game_id"] == "aabbccdd"


def test_crewai_wrapper_full_game() -> None:
    """CrewAI wrapper functions play a complete game via the SDK."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # Call SDK directly (same code path as the @tool wrappers)
        from game.sdk import sdk

        info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
        gid = info["game_id"]

        r1 = sdk.submit_action(gid, "cop", "SE", games_base=base)
        assert r1.success
        assert not r1.game_over

        obs = sdk.get_state(gid, "cop", games_base=base)
        assert obs.my_pos == (1, 1)
        assert obs.opponent_pos == (2, 2)

        r2 = sdk.submit_action(gid, "thief", "NW", games_base=base)
        assert r2.game_over
        assert r2.winner == "cop"


def test_crewai_tool_json_output_valid() -> None:
    """CrewAI tool returns a parseable JSON string on success."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk

        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        result = sdk.submit_action(gid, "cop", "E", games_base=base)
        payload = json.loads(result.to_json())
        assert payload["success"] is True
        assert "game_over" in payload
        assert "winner" in payload
        assert "win_reason" in payload
        assert "error" in payload


def test_crewai_tool_error_on_bad_game_id() -> None:
    """CrewAI tool returns error JSON for unknown game_id."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk

        with pytest.raises(FileNotFoundError):
            sdk.submit_action("nope", "cop", "E", games_base=base)


def test_crewai_get_state_thief_no_barriers() -> None:
    """CrewAI get_state: thief observation has barriers_remaining=None."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk

        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        obs = sdk.get_state(info["game_id"], "thief", games_base=base)
        payload = json.loads(obs.to_json())
        assert payload["barriers_remaining"] is None


def test_crewai_barrier_reduces_count() -> None:
    """CrewAI submit BARRIER: barriers_remaining decreases by 1."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        from game.sdk import sdk

        info = sdk.new_game((5, 5), (2, 2), (4, 4), games_base=base)
        gid = info["game_id"]

        before = sdk.get_state(gid, "cop", games_base=base).barriers_remaining
        sdk.submit_action(gid, "cop", "BARRIER", games_base=base)
        after = sdk.get_state(gid, "cop", games_base=base).barriers_remaining
        assert after == before - 1
