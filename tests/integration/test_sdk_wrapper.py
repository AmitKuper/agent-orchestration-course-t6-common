"""Integration tests: full games played through the SDK layer."""

import json
import tempfile
from pathlib import Path

import pytest

from game.sdk import sdk


def _sdk(tmp: str) -> Path:
    """Return a base path for isolated game storage."""
    return Path(tmp)


def test_sdk_full_game_cop_captures() -> None:
    """SDK: cop captures thief on a 3x3 grid in 2 moves."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
        gid = info["game_id"]

        r1 = sdk.submit_action(gid, "cop", "SE", games_base=base)
        assert r1.success
        assert not r1.game_over

        r2 = sdk.submit_action(gid, "thief", "NW", games_base=base)
        assert r2.game_over
        assert r2.winner == "cop"
        assert r2.win_reason == "capture"


def test_sdk_full_game_thief_survives() -> None:
    """SDK: thief evades until max_moves."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), {"max_moves": 2}, games_base=base)
        gid = info["game_id"]

        sdk.submit_action(gid, "cop", "E", games_base=base)
        sdk.submit_action(gid, "thief", "W", games_base=base)
        sdk.submit_action(gid, "cop", "W", games_base=base)
        r = sdk.submit_action(gid, "thief", "E", games_base=base)
        assert r.game_over
        assert r.winner == "thief"
        assert r.win_reason == "thief_survived"


def test_sdk_illegal_move_does_not_advance_state() -> None:
    """SDK: illegal action returns failure and state.json is not updated."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        state_before = json.loads(
            (base / gid / "state.json").read_text()
        )
        r = sdk.submit_action(gid, "cop", "N", games_base=base)  # off-grid
        assert not r.success
        state_after = json.loads(
            (base / gid / "state.json").read_text()
        )
        assert state_before == state_after


def test_sdk_log_appended_for_every_call() -> None:
    """SDK: game.log grows by one line per submit_action regardless of success."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        sdk.submit_action(gid, "cop", "N", games_base=base)   # illegal
        sdk.submit_action(gid, "cop", "E", games_base=base)   # legal
        sdk.submit_action(gid, "thief", "W", games_base=base) # legal

        lines = (base / gid / "game.log").read_text().splitlines()
        # 1 setup entry + 3 turn entries
        assert len(lines) == 4


def test_sdk_get_state_reflects_moves() -> None:
    """SDK: get_state returns updated positions after moves."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        sdk.submit_action(gid, "cop", "E", games_base=base)
        obs = sdk.get_state(gid, "cop", games_base=base)
        assert obs.my_pos == (1, 0)


def test_sdk_state_hash_consistent() -> None:
    """SDK: state_hash matches between two load-hash cycles without moves."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        h1 = sdk.state_hash(gid, games_base=base)
        h2 = sdk.state_hash(gid, games_base=base)
        assert h1 == h2


def test_sdk_state_hash_changes_after_move() -> None:
    """SDK: state_hash changes after a successful action."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]

        h1 = sdk.state_hash(gid, games_base=base)
        sdk.submit_action(gid, "cop", "E", games_base=base)
        h2 = sdk.state_hash(gid, games_base=base)
        assert h1 != h2


def test_sdk_missing_game_raises() -> None:
    """SDK: submit_action raises FileNotFoundError for unknown game_id."""
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            sdk.submit_action("doesnotexist", "cop", "E", games_base=Path(tmp))


def test_sdk_barrier_appears_in_log() -> None:
    """SDK: BARRIER action is logged correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        base = _sdk(tmp)
        info = sdk.new_game((5, 5), (2, 2), (4, 4), games_base=base)
        gid = info["game_id"]

        sdk.submit_action(gid, "cop", "BARRIER", games_base=base)
        # game.log has setup + turn entries; find the turn entry
        lines = (base / gid / "game.log").read_text().splitlines()
        entries = [json.loads(ln) for ln in lines]
        turn = next(e for e in entries if e.get("type") == "turn")
        assert turn["action"] == "barrier"
        assert turn["success"] is True
