"""Unit tests for game.gmail.reporter."""

import json
import tempfile
from pathlib import Path

from game.gmail.reporter import build_report, write_report_file

_SUB_GAMES = [
    {"game_id": "g1", "winner": "cop", "scores": {"cop": 20, "thief": 5}},
    {"game_id": "g2", "winner": "thief", "scores": {"cop": 5, "thief": 10}},
]


def test_build_internal_report_has_required_keys() -> None:
    """Internal report contains all top-level PRD §10 keys."""
    report = build_report(_SUB_GAMES, report_type="internal")
    for key in ("group_name", "sub_games", "totals", "played_at", "timezone"):
        assert key in report


def test_build_internal_report_totals_correct() -> None:
    """Totals are summed correctly across sub-games."""
    report = build_report(_SUB_GAMES)
    assert report["totals"]["cop"] == 25
    assert report["totals"]["thief"] == 15


def test_build_bonus_report_has_required_keys() -> None:
    """Bonus report contains bonus-specific keys."""
    report = build_report(_SUB_GAMES, report_type="bonus")
    for key in ("report_type", "groups", "students_group_1", "totals_by_group"):
        assert key in report
    assert report["report_type"] == "bonus_game"


def test_build_report_sub_games_preserved() -> None:
    """Sub-games list is preserved in output."""
    report = build_report(_SUB_GAMES)
    assert report["sub_games"] == _SUB_GAMES


def test_write_report_file_creates_json() -> None:
    """write_report_file writes valid JSON to report.json."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        report = build_report(_SUB_GAMES)
        path = write_report_file(report, "test_game", games_base=base)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["totals"]["cop"] == 25


def test_write_report_file_path() -> None:
    """write_report_file places the file at games/<game_id>/report.json."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        path = write_report_file({"x": 1}, "mygame", games_base=base)
        assert path == base / "mygame" / "report.json"


def test_build_report_empty_sub_games() -> None:
    """Empty sub-games list yields zero totals."""
    report = build_report([])
    assert report["totals"]["cop"] == 0
    assert report["totals"]["thief"] == 0
