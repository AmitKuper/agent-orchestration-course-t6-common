"""Unit tests for persistence helpers."""

import json
import tempfile
from pathlib import Path

import pytest

from game.game import Game
from game.persistence import (
    append_log,
    generate_game_id,
    load_state,
    save_state,
)
from game.state import ActionResult


def make_game() -> Game:
    """Create a simple test game."""
    return Game.new("abc123", (5, 5), (0, 0), (4, 4))


def test_generate_game_id_is_8_chars() -> None:
    """generate_game_id returns an 8-character hex string."""
    gid = generate_game_id()
    assert len(gid) == 8
    int(gid, 16)  # must be valid hex


def test_generate_game_id_unique() -> None:
    """Two IDs are not equal (extremely high probability)."""
    assert generate_game_id() != generate_game_id()


def test_save_and_load_roundtrip() -> None:
    """save_state then load_state restores an identical game."""
    g = make_game()
    g.submit_action("cop", "E")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        restored = load_state("abc123", base)

    assert restored.to_dict() == g.to_dict()


def test_load_missing_raises() -> None:
    """load_state raises FileNotFoundError for unknown game_id."""
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            load_state("nope", Path(tmp))


def test_append_log_creates_jsonl() -> None:
    """append_log writes a valid JSONL line."""
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        append_log("abc123", "cop", "E", result, base=base)
        log_path = base / "abc123" / "game.log"
        assert log_path.exists()
        line = json.loads(log_path.read_text().strip())
        assert line["actor"] == "cop"
        assert line["action"] == "E"
        assert line["success"] is True


def test_append_log_multiple_entries() -> None:
    """append_log appends; each line is valid JSON."""
    result = ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for action in ["N", "E", "S"]:
            append_log("abc123", "cop", action, result, base=base)
        lines = (base / "abc123" / "game.log").read_text().strip().splitlines()
        assert len(lines) == 3
        actions = [json.loads(line)["action"] for line in lines]
        assert actions == ["N", "E", "S"]
