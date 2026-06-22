"""Unit tests for persistence helpers."""

import json
import tempfile
from pathlib import Path

import pytest

from game.constants import compute_scores
from game.game import Game
from game.persistence import (
    append_log,
    append_terminal_log,
    generate_game_id,
    load_state,
    save_state,
)
from game.state import ActionResult


def make_game() -> Game:
    """Create a simple test game."""
    return Game.new("abc123", (5, 5), (0, 0), (4, 4))


def _ok_result() -> ActionResult:
    """Return a successful non-terminal ActionResult."""
    return ActionResult(success=True, error=None, game_over=False, winner=None, win_reason=None)


def _game_over_result(winner: str, reason: str) -> ActionResult:
    """Return a game-over ActionResult."""
    return ActionResult(success=True, error=None, game_over=True, winner=winner, win_reason=reason)


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


def test_append_log_prd_format() -> None:
    """append_log writes a JSONL line matching the PRD per-turn schema."""
    result = _ok_result()
    g = make_game()
    g.submit_action("cop", "E")  # advance state so turn > 0

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        append_log("abc123", "cop", "E", result, (0, 0), (1, 0), g, base=base)
        log_path = base / "abc123" / "game.log"
        assert log_path.exists()
        line = json.loads(log_path.read_text().strip())

        assert line["actor"] == "cop"
        assert line["action"] == "move"
        assert line["from"] == [0, 0]
        assert line["to"] == [1, 0]
        assert line["barrier_at"] is None
        assert line["message"] is None
        assert "state_after" in line
        assert "cop" in line["state_after"]
        assert "thief" in line["state_after"]
        assert "barriers" in line["state_after"]


def test_append_log_barrier_entry() -> None:
    """append_log for a BARRIER action records barrier_at correctly."""
    g = Game.new("abc123", (5, 5), (2, 2), (4, 4))
    result = g.submit_action("cop", "BARRIER")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        append_log("abc123", "cop", "BARRIER", result, (2, 2), (2, 2), g, base=base)
        line = json.loads((base / "abc123" / "game.log").read_text().strip())
        assert line["action"] == "barrier"
        assert line["barrier_at"] == [2, 2]
        assert line["from"] == [2, 2]
        assert line["to"] == [2, 2]


def test_append_log_multiple_entries() -> None:
    """append_log appends; each line is valid JSON."""
    g = make_game()
    result = _ok_result()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        cases = [("E", (0, 0), (1, 0)), ("N", (1, 0), (1, 0)), ("S", (1, 0), (1, 1))]
        for action, frm, to in cases:
            append_log("abc123", "cop", action, result, frm, to, g, base=base)
        lines = (base / "abc123" / "game.log").read_text().strip().splitlines()
        assert len(lines) == 3
        actions = [json.loads(line)["action"] for line in lines]
        assert actions == ["move", "move", "move"]


def test_append_terminal_log_cop_wins() -> None:
    """append_terminal_log writes a terminal entry when cop wins."""
    g = make_game()
    result = _game_over_result("cop", "capture")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        append_terminal_log("abc123", result, g, base=base)
        line = json.loads((base / "abc123" / "game.log").read_text().strip())
        assert line["type"] == "terminal"
        assert line["winner"] == "cop"
        assert line["win_reason"] == "capture"
        assert line["scores"] == {"cop": 20, "thief": 5}
        assert "rounds" in line
        assert "barriers_used" in line


def test_append_terminal_log_thief_wins() -> None:
    """append_terminal_log writes correct scores when thief wins."""
    g = make_game()
    result = _game_over_result("thief", "thief_survived")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_state(g, base)
        append_terminal_log("abc123", result, g, base=base)
        line = json.loads((base / "abc123" / "game.log").read_text().strip())
        assert line["scores"] == {"cop": 5, "thief": 10}


def test_compute_scores_cop_wins() -> None:
    """compute_scores returns correct points when cop wins."""
    assert compute_scores("cop", {}) == {"cop": 20, "thief": 5}


def test_compute_scores_thief_wins() -> None:
    """compute_scores returns correct points when thief wins."""
    assert compute_scores("thief", {}) == {"cop": 5, "thief": 10}


def test_compute_scores_custom_mechanics() -> None:
    """compute_scores respects scoring overrides in mechanics."""
    mech = {"scoring": {"cop_win": 30, "thief_loss": 2}}
    scores = compute_scores("cop", mech)
    assert scores == {"cop": 30, "thief": 2}
