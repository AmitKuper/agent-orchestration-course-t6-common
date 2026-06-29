"""Post-match notification and report helpers for run_match.py."""

from __future__ import annotations

import json
import os

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

from match_helpers import API_KEY
from match_helpers.log_reader import _find_game_logs


def _collect_game_logs(sub_games: list[dict]) -> str:
    """Return concatenated game.log contents for all sub-games found on disk.

    Args:
        sub_games: List of sub-game result dicts containing "sg_id".

    Returns:
        Plain-text block with each sub-game log separated by a header.
    """
    blocks: list[str] = []
    for sg in sub_games:
        sg_id = sg.get("sg_id") or f"match_sg{sg.get('sub_game', '?'):02}"
        matches = _find_game_logs(sg_id)
        if not matches:
            continue
        try:
            content = matches[0].read_text(encoding="utf-8").strip()
        except OSError:
            continue
        blocks.append(f"=== {sg_id} ===\n{content}")
    return "\n\n".join(blocks)


def _build_results_summary(sub_games: list[dict]) -> str:
    """Build a compact per-sub-game results table for the email log.

    Args:
        sub_games: List of sub-game result dicts from _run_series.

    Returns:
        Formatted string with one line per sub-game.
    """
    lines = []
    for sg in sub_games:
        n = sg.get("sub_game", "?")
        a_role = sg.get("initiator_role", "?")
        b_role = "cop" if a_role == "thief" else "thief"
        winner = sg.get("winner") or "none"
        reason = sg.get("win_reason") or "technical_loss"
        rounds = sg.get("rounds") or "?"
        cop_pts = sg.get("scores", {}).get("cop", 0)
        thief_pts = sg.get("scores", {}).get("thief", 0)
        lines.append(
            f"  #{n:02}  winner={winner:<6}  ({reason:<16})  "
            f"A={a_role:<5} B={b_role:<5}  "
            f"rounds={rounds:<3}  cop={cop_pts}pts  thief={thief_pts}pts"
        )
    return "\n".join(lines)


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


async def _notify_both_servers(
    url_a: str, url_b: str, series_id: str,
    winner_name: str, cop_total: int, thief_total: int,
    num_sg: int, results_log: str = "",
    name_a: str = "", name_b: str = "",
    members_a: str = "", members_b: str = "",
) -> None:
    """Call send_game_summary on both servers so each sends its own result email.

    Args:
        url_a: Server A base URL.
        url_b: Server B base URL.
        series_id: Match series identifier.
        winner_name: Display name of the winning player.
        cop_total: Total cop score across all sub-games.
        thief_total: Total thief score across all sub-games.
        num_sg: Number of valid sub-games played.
        results_log: Per-sub-game results table to include in the email.
        name_a: Server A's player name.
        name_b: Server B's player name.
        members_a: Server A's team member names.
        members_b: Server B's team member names.
    """
    from fastmcp.exceptions import ToolError

    auth = BearerAuth(API_KEY)
    base = {
        "series_id": series_id, "winner_name": winner_name,
        "cop_total": cop_total, "thief_total": thief_total,
        "num_sub_games": num_sg, "results_log": results_log,
    }
    targets = ((url_a, name_b, members_b), (url_b, name_a, members_a))
    for url, opponent_name, opponent_members in targets:
        payload = {**base, "opponent_name": opponent_name,
                   "opponent_members": opponent_members}
        async with Client(url + "/mcp", auth=auth, timeout=30.0) as c:
            try:
                result = await c.call_tool("send_game_summary", payload)
            except ToolError as exc:
                if "opponent" not in str(exc):
                    print(f"[gmail] {url}: skipped — {exc}")
                    continue
                result = await c.call_tool("send_game_summary", base)
            txt = result.content[0].text if result.content else "{}"
            print(f"[gmail] {url}: {txt}")


def _maybe_send_report(sub_games: list[dict], series_id: str,
                       game_type: str = "internal") -> None:
    """Send the match report via Gmail if GMAIL_ENABLED=true and GMAIL_RECIPIENT is set."""
    from game.gmail.gmail_plugin import is_enabled
    if not is_enabled():
        print("[report] Gmail disabled — set GMAIL_ENABLED=true and GMAIL_RECIPIENT to enable.")
        return
    from game.gmail.reporter import build_report
    from game.gmail.sender import send_report
    report = build_report(sub_games, report_type=game_type)
    send_report(report)
    print(f"[report] Sent to {os.environ.get('GMAIL_RECIPIENT')}")
