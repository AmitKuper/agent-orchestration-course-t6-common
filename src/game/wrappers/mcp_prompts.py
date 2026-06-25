"""MCP prompt registrations — role-specific rulebook prompts for LLM grounding.

Registers cop_rules and thief_rules FastMCP prompts that ground each agent
in the full game rulebook and its specific win conditions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

_RULES_COMMON = (
    "Grid: 5×5, coordinates [col, row] 0-indexed, origin top-left.\n"
    "Each round: thief moves first, then cop.\n"
    "Moves: N NE E SE S SW W NW (one step each direction).\n"
    "Barrier: cop only, max 5 per game, placed on current cell (BARRIER action).\n"
    "Stay: thief only, pass the turn without moving (STAY action).\n"
    "Win conditions:\n"
    "  Cop wins — lands on thief cell (capture).\n"
    "  Thief wins — survives 25 rounds or cop has no moves and no barriers left.\n"
    "Always reply with one intent sentence, then on a new line: Action: <MOVE>\n"
)

_COP_ROLE = (
    "You are the COP. Your goal is to capture the thief by sharing its cell.\n"
    "You may play BARRIER on your current cell to slow the thief (max 5 per game).\n"
    "Partial observation: you can only see the thief when it is within 1 cell "
    "(Chebyshev distance). When the thief is out of range, opponent_pos is null — "
    "reason from the last known position and barriers.\n"
)

_THIEF_ROLE = (
    "You are the THIEF. Your goal is to survive 25 rounds without being captured.\n"
    "You cannot place barriers. You always see the cop's exact position.\n"
    "Use STAY to pass a turn and bait the cop into committing to a direction.\n"
)


def register_prompts(mcp: FastMCP) -> None:
    """Register cop_rules and thief_rules MCP prompts on the server.

    Args:
        mcp: The FastMCP server instance to attach prompts to.
    """
    @mcp.prompt()
    def cop_rules(game_id: str = "") -> str:
        """System prompt grounding the cop agent in game rules and role.

        Args:
            game_id: Active game identifier included in the context header.

        Returns:
            Full system prompt string for the cop role.
        """
        header = f"Game: {game_id}\n" if game_id else ""
        return header + _COP_ROLE + _RULES_COMMON

    @mcp.prompt()
    def thief_rules(game_id: str = "") -> str:
        """System prompt grounding the thief agent in game rules and role.

        Args:
            game_id: Active game identifier included in the context header.

        Returns:
            Full system prompt string for the thief role.
        """
        header = f"Game: {game_id}\n" if game_id else ""
        return header + _THIEF_ROLE + _RULES_COMMON
