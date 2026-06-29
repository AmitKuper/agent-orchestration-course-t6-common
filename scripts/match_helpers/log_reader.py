"""Game log reading helpers for run_match.py."""

from __future__ import annotations

import json
from pathlib import Path

from match_helpers import REPO_ROOT


def _find_game_logs(sg_id: str) -> list[Path]:
    """Return all game.log paths for sg_id across any games subdirectory.

    Args:
        sg_id: Sub-game identifier.

    Returns:
        Sorted list of matching game.log paths.
    """
    return sorted(set((REPO_ROOT / "games").rglob(f"{sg_id}/game.log")))


def _read_terminal(sg_id: str) -> dict:
    """Read the terminal log entry for sg_id from any games subdirectory."""
    for log_path in _find_game_logs(sg_id):
        for raw in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if raw.strip():
                entry = json.loads(raw)
                if entry.get("type") == "terminal":
                    return entry
    return {}


def _read_game_log(sg_id: str) -> list[dict]:
    """Return all parsed log entries for sg_id from the first log found on disk.

    Args:
        sg_id: Sub-game identifier.

    Returns:
        List of dicts (one per log line), empty if no log exists.
    """
    for log_path in _find_game_logs(sg_id):
        entries = []
        for raw in log_path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                entries.append(json.loads(raw))
        if entries:
            return entries
    return []


def _count_rounds(sg_id: str) -> int:
    """Count completed rounds (thief turns) from a sub-game log on disk.

    Fallback when no terminal entry exists — e.g. a game truncated by the
    orchestrator's max-rounds cap. The engine advances once per thief action.

    Args:
        sg_id: Sub-game identifier.

    Returns:
        Number of thief turn entries, or 0 if no log is found.
    """
    for log_path in _find_game_logs(sg_id):
        count = 0
        for raw in log_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            entry = json.loads(raw)
            if entry.get("type") == "turn" and entry.get("actor") == "thief":
                count += 1
        if count:
            return count
    return 0


def _board_str(sg_id: str) -> str:
    """Return a compact ASCII board string from the latest game log entry."""
    for server in ("server_a", "server_b"):
        log_path = REPO_ROOT / "games" / server / sg_id / "game.log"
        if not log_path.exists():
            continue
        for raw in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if not raw.strip():
                continue
            e = json.loads(raw)
            if e.get("type") != "turn" or "state_after" not in e:
                continue
            sa = e["state_after"]
            cols, rows = 5, 5
            barriers = {tuple(b) for b in sa.get("barriers", [])}
            cop = tuple(sa["cop"])
            thief = tuple(sa["thief"])
            lines = ["  " + " ".join(str(c) for c in range(cols))]
            for r in range(rows):
                row = [str(r)]
                for c in range(cols):
                    cell = (c, r)
                    if cell == cop and cell == thief:
                        row.append("X")
                    elif cell == cop:
                        row.append("C")
                    elif cell == thief:
                        row.append("T")
                    elif cell in barriers:
                        row.append("#")
                    else:
                        row.append(".")
                lines.append(" ".join(row))
            return "\n".join(lines)
    return ""
