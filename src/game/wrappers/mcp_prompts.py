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
    "Win conditions:\n"
    "  Cop wins — lands on thief (capture) or thief has no legal moves (trapped).\n"
    "  Thief wins — survives 25 rounds or cop has no moves and no barriers left.\n"
    "Always reply with one intent sentence, then on a new line: Action: <MOVE>\n"
)

_COP_ROLE = (
    "You are the COP. Your goal is to capture the thief by sharing its cell.\n"
    "You may also play BARRIER on your current cell to restrict thief movement "
    "(max 5 barriers per game).\n"
)

_THIEF_ROLE = (
    "You are the THIEF. Your goal is to survive 25 rounds without being captured.\n"
    "You cannot place barriers — focus on evasion and preserving open-space options.\n"
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
