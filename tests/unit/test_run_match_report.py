"""Unit tests for match_helpers log discovery and summary functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# match_helpers lives in scripts/ which is not a package on the Python path
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import match_helpers.log_reader as log_reader  # noqa: E402
import match_helpers.notifier as notifier  # noqa: E402


def _write_log(games: Path, subdir: str, sg_id: str, lines: list[dict]) -> None:
    """Write a JSONL game.log under games/<subdir>/<sg_id>/game.log."""
    log_dir = games / subdir / sg_id
    log_dir.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(line) for line in lines)
    (log_dir / "game.log").write_text(text + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def patch_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect REPO_ROOT in log_reader to a temporary directory."""
    monkeypatch.setattr(log_reader, "REPO_ROOT", tmp_path)


def test_find_game_logs_finds_port_named_subdir(tmp_path: Path) -> None:
    """_find_game_logs locates logs under games/server_<port>/ (not server_a)."""
    _write_log(tmp_path / "games", "server_8001", "matchX_sg01", [{"type": "setup"}])
    found = log_reader._find_game_logs("matchX_sg01")
    assert len(found) == 1
    assert found[0].name == "game.log"


def test_count_rounds_counts_thief_turns(tmp_path: Path) -> None:
    """_count_rounds returns the number of thief turn entries (one per round)."""
    lines = [
        {"type": "setup"},
        {"type": "turn", "actor": "thief"},
        {"type": "turn", "actor": "cop"},
        {"type": "turn", "actor": "thief"},
        {"type": "turn", "actor": "cop"},
    ]
    _write_log(tmp_path / "games", "server_8001", "matchX_sg02", lines)
    assert log_reader._count_rounds("matchX_sg02") == 2


def test_read_terminal_returns_entry(tmp_path: Path) -> None:
    """_read_terminal extracts the terminal entry regardless of subdir name."""
    lines = [
        {"type": "setup"},
        {"type": "turn", "actor": "thief"},
        {"type": "terminal", "winner": "cop", "rounds": 7, "barriers_used": 2},
    ]
    _write_log(tmp_path / "games", "server_8002", "matchX_sg03", lines)
    terminal = log_reader._read_terminal("matchX_sg03")
    assert terminal["winner"] == "cop"
    assert terminal["rounds"] == 7


def test_build_results_summary_renders_incomplete() -> None:
    """Incomplete sub-games show winner=none and the incomplete reason."""
    sub_games = [{
        "sub_game": 1, "initiator_role": "thief", "winner": None,
        "win_reason": "incomplete", "rounds": 2,
        "scores": {"cop": 0, "thief": 0},
    }]
    summary = notifier._build_results_summary(sub_games)
    assert "incomplete" in summary
    assert "none" in summary
    assert "rounds=2" in summary
