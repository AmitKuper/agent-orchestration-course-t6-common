"""Unit tests for run_match.py report helpers (log discovery + summaries)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_RUN_MATCH = Path(__file__).resolve().parents[2] / "scripts" / "run_match.py"


def _load_run_match() -> ModuleType:
    """Import scripts/run_match.py as a standalone module."""
    spec = importlib.util.spec_from_file_location("run_match", _RUN_MATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_log(games: Path, subdir: str, sg_id: str, lines: list[dict]) -> None:
    """Write a JSONL game.log under games/<subdir>/<sg_id>/game.log."""
    log_dir = games / subdir / sg_id
    log_dir.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(line) for line in lines)
    (log_dir / "game.log").write_text(text + "\n", encoding="utf-8")


@pytest.fixture
def rm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load run_match with _REPO_ROOT pointed at a temporary directory."""
    module = _load_run_match()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)
    return module


def test_find_game_logs_finds_port_named_subdir(rm: ModuleType, tmp_path: Path) -> None:
    """_find_game_logs locates logs under games/server_<port>/ (not server_a)."""
    _write_log(tmp_path / "games", "server_8001", "matchX_sg01", [{"type": "setup"}])
    found = rm._find_game_logs("matchX_sg01")
    assert len(found) == 1
    assert found[0].name == "game.log"


def test_count_rounds_counts_thief_turns(rm: ModuleType, tmp_path: Path) -> None:
    """_count_rounds returns the number of thief turn entries (one per round)."""
    lines = [
        {"type": "setup"},
        {"type": "turn", "actor": "thief"},
        {"type": "turn", "actor": "cop"},
        {"type": "turn", "actor": "thief"},
        {"type": "turn", "actor": "cop"},
    ]
    _write_log(tmp_path / "games", "server_8001", "matchX_sg02", lines)
    assert rm._count_rounds("matchX_sg02") == 2


def test_read_terminal_returns_entry(rm: ModuleType, tmp_path: Path) -> None:
    """_read_terminal extracts the terminal entry regardless of subdir name."""
    lines = [
        {"type": "setup"},
        {"type": "turn", "actor": "thief"},
        {"type": "terminal", "winner": "cop", "rounds": 7, "barriers_used": 2},
    ]
    _write_log(tmp_path / "games", "server_8002", "matchX_sg03", lines)
    terminal = rm._read_terminal("matchX_sg03")
    assert terminal["winner"] == "cop"
    assert terminal["rounds"] == 7


def test_build_results_summary_renders_incomplete(rm: ModuleType) -> None:
    """Incomplete sub-games show winner=none and the incomplete reason."""
    sub_games = [{
        "sub_game": 1, "initiator_role": "thief", "winner": None,
        "win_reason": "incomplete", "rounds": 2,
        "scores": {"cop": 0, "thief": 0},
    }]
    summary = rm._build_results_summary(sub_games)
    assert "incomplete" in summary
    assert "none" in summary
    assert "rounds=2" in summary
