"""Reporter — builds the PRD §10 JSON report from sub-game results."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_report(
    sub_games: list[dict[str, Any]],
    report_type: str = "internal",
) -> dict[str, Any]:
    """Build the final match report dict matching the PRD §10 schema.

    Args:
        sub_games: List of per-sub-game result dicts (see PRD §10).
        report_type: "internal" or "bonus".

    Returns:
        Report dict ready for JSON serialisation and email body.
    """
    played_at = datetime.now(UTC).astimezone().isoformat()
    totals = _compute_totals(sub_games)

    if report_type == "bonus":
        return _build_bonus_report(sub_games, played_at, totals)
    return _build_internal_report(sub_games, played_at, totals)


def _compute_totals(sub_games: list[dict[str, Any]]) -> dict[str, int]:
    """Sum scores across all sub-games by role."""
    totals: dict[str, int] = {"cop": 0, "thief": 0}
    for sg in sub_games:
        scores = sg.get("scores", {})
        totals["cop"] += int(scores.get("cop", 0))
        totals["thief"] += int(scores.get("thief", 0))
    return totals


def _parse_player_names(names_env: str) -> list[str]:
    """Split PLAYER_NAMES env value (e.g. 'Alice & Bob') into a list.

    Args:
        names_env: Raw env string, members separated by '&' or ','.

    Returns:
        List of stripped non-empty name strings.
    """
    sep = "&" if "&" in names_env else ","
    return [n.strip() for n in names_env.split(sep) if n.strip()]


def _build_internal_report(
    sub_games: list[dict[str, Any]],
    played_at: str,
    totals: dict[str, int],
) -> dict[str, Any]:
    """Build internal-game report shape."""
    return {
        "group_name": os.environ.get("GROUP_NAME", ""),
        "students": _parse_player_names(os.environ.get("PLAYER_NAMES", "")),
        "github_repo": os.environ.get("GITHUB_REPO", ""),
        "cop_mcp_url": os.environ.get("COP_MCP_URL", ""),
        "thief_mcp_url": os.environ.get("THIEF_MCP_URL", ""),
        "timezone": "Asia/Jerusalem",
        "played_at": played_at,
        "sub_games": sub_games,
        "totals": totals,
    }


def _build_bonus_report(
    sub_games: list[dict[str, Any]],
    played_at: str,
    totals: dict[str, int],
) -> dict[str, Any]:
    """Build bonus inter-group report shape."""
    return {
        "report_type": "bonus_game",
        "groups": {
            "group_1": os.environ.get("GROUP_NAME", ""),
            "group_2": os.environ.get("OPPONENT_GROUP_NAME", ""),
        },
        "timezone": "Asia/Jerusalem",
        "played_at": played_at,
        "students_group_1": _parse_player_names(os.environ.get("PLAYER_NAMES", "")),
        "students_group_2": [],
        "sub_games": sub_games,
        "totals_by_group": totals,
        "mutual_agreement": False,
    }


def write_report_file(
    report: dict[str, Any],
    game_id: str,
    games_base: Path | None = None,
) -> Path:
    """Write the report dict to games/<game_id>/report.json.

    Args:
        report: The built report dict.
        game_id: The match game identifier.
        games_base: Optional override for the games root directory.

    Returns:
        Path to the written report.json file.
    """
    base = games_base or Path("games")
    path = base / game_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
