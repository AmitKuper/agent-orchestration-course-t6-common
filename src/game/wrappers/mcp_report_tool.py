"""MCP tool for sending a human-readable game summary email from each server."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_report_tool(mcp: FastMCP) -> None:
    """Register the send_game_summary tool on the MCP server.

    Args:
        mcp: The FastMCP server instance to attach the tool to.
    """
    @mcp.tool()
    def send_game_summary(
        series_id: str,
        winner_name: str,
        cop_total: int,
        thief_total: int,
        num_sub_games: int,
        results_log: str = "",
        opponent_name: str = "",
    ) -> str:
        """Send a human-readable result email from this server's player perspective.

        Reads PLAYER_NAME from env for the sender identity.
        Sends to GMAIL_RECIPIENT. No-ops silently if Gmail is disabled.

        Args:
            series_id: The match series identifier.
            winner_name: Display name of the winning player.
            cop_total: Total cop score across all sub-games.
            thief_total: Total thief score across all sub-games.
            num_sub_games: Number of valid sub-games played.
            results_log: Per-sub-game results table to append to the email.
            opponent_name: Display name of the opposing player (for the subject).

        Returns:
            JSON {"sent": True, "from": name} on success, or {"error": ...}.
        """
        from game.gmail.gmail_plugin import get_recipient, is_enabled
        from game.gmail.sender import send_email

        try:
            if not is_enabled():
                return json.dumps({"sent": False, "reason": "Gmail disabled"})
            player_name = os.environ.get("PLAYER_NAME", "Unknown Player")
            recipient = get_recipient()
            opponent = opponent_name or "Opponent"
            subject = f"Game Result {player_name} vs {opponent} | Series {series_id}"
            body = _build_body(
                player_name, series_id, winner_name,
                cop_total, thief_total, num_sub_games, results_log, opponent,
            )
            send_email(recipient, subject, body)
            return json.dumps({"sent": True, "from": player_name, "to": recipient})
        except Exception as exc:
            return json.dumps({"error": str(exc)})


def _build_body(
    player_name: str,
    series_id: str,
    winner_name: str,
    cop_total: int,
    thief_total: int,
    num_sub_games: int,
    results_log: str = "",
    opponent_name: str = "Opponent",
) -> str:
    """Build the plain-text email body for a game result summary.

    Args:
        player_name: This server's player name.
        series_id: Match series ID.
        winner_name: The winning player's display name.
        cop_total: Total cop score.
        thief_total: Total thief score.
        num_sub_games: Sub-games played.
        results_log: Per-sub-game results table to append.
        opponent_name: Display name of the opposing player.

    Returns:
        Formatted plain-text body string.
    """
    lines = [
        f"Game Report from: {player_name}",
        f"Series ID:        {series_id}",
        f"Sub-games played: {num_sub_games}",
        "",
        "Final Scores:",
        f"  Cop:   {cop_total} pts",
        f"  Thief: {thief_total} pts",
        "",
        f"*** WINNER: {winner_name} ***",
    ]
    if results_log:
        lines += ["", "Sub-game Results:", results_log]
    lines += ["", "Sent automatically by the Cop & Thief MCP game engine."]
    lines += [f"The playing teams are: {player_name} vs {opponent_name}"]
    return "\n".join(lines)
