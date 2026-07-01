"""Post-match notification and report helpers for run_match.py."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

from match_helpers import API_KEY


async def _fetch_player_info(url: str, fallback: str) -> tuple[str, str]:
    """Query a server's get_player_name tool for its team name and members.

    Args:
        url: Base URL of the server to query.
        fallback: Team name to return if the tool is missing or errors.

    Returns:
        (team_name, player_members); team_name falls back, members may be "".
    """
    auth = BearerAuth(API_KEY)
    try:
        async with Client(url + "/mcp", auth=auth, timeout=10.0) as c:
            result = await c.call_tool("get_player_name", {})
            txt = result.content[0].text if result.content else "{}"
            data = json.loads(txt)
            return data.get("player_name") or fallback, data.get("player_members") or ""
    except Exception:
        return fallback, ""


def _maybe_send_report(sub_games: list[dict], series_id: str,
                       game_type: str = "internal") -> None:
    """Build the JSON report, save it to disk, and email it if Gmail is enabled.

    Saves the report to games/<series_id>/email_sent.json regardless of whether
    Gmail is enabled, so the content can always be inspected locally.

    Args:
        sub_games: List of sub-game result dicts from _run_series.
        series_id: Match series identifier (used as the save directory name).
        game_type: "internal" or "bonus" — selects the report schema.
    """
    from game.gmail.reporter import build_report
    report = build_report(sub_games, report_type=game_type)

    out_path = Path("games") / series_id / "email_sent.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[report] Saved to {out_path}")

    from game.gmail.gmail_plugin import is_enabled
    if not is_enabled():
        print("[report] Gmail disabled — set GMAIL_ENABLED=true and GMAIL_RECIPIENT to enable.")
        return
    from game.gmail.sender import send_report
    send_report(report)
    print(f"[report] Sent to {os.environ.get('GMAIL_RECIPIENT')}")
