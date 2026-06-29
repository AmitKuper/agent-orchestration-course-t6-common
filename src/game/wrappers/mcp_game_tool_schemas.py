"""Unified tool definition schemas for the Cop & Thief MCP game tools.

Extracted from mcp_agent_tools.py to keep each module under 150 lines.
Follows the Anthropic input_schema convention; to_ollama_tools() converts
these at call time for the Ollama backend.
"""

from __future__ import annotations

GAME_TOOLS: list[dict] = [
    {
        "name": "get_state",
        "description": (
            "Get the current observation state for your role. "
            "Call this at the start of your turn to see your position, "
            "the opponent's last known position, legal moves, and barriers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "string", "description": "The game identifier."},
                "actor": {"type": "string", "description": "'cop' or 'thief'."},
            },
            "required": ["game_id", "actor"],
        },
    },
    {
        "name": "take_action",
        "description": (
            "Submit your chosen action for this turn. "
            "Valid actions: N NE E SE S SW W NW (movement), "
            "BARRIER (cop only, places barrier on current cell), "
            "or STAY (thief only, remain on current cell for one turn). "
            "Include a short natural-language message describing your intent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "string", "description": "The game identifier."},
                "actor": {"type": "string", "description": "'cop' or 'thief'."},
                "action": {"type": "string", "description": "Move direction, BARRIER, or STAY."},
                "message": {"type": "string", "description": "Brief intent message."},
            },
            "required": ["game_id", "actor", "action"],
        },
    },
    {
        "name": "get_actor_action",
        "description": (
            "Get the actor backend's recommended action without applying it. "
            "Orchestrator uses this to retrieve the Q-table decision, then generates "
            "a NL message client-side before calling take_action (PRD §6)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "string", "description": "The game identifier."},
                "actor": {"type": "string", "description": "'cop' or 'thief'."},
            },
            "required": ["game_id", "actor"],
        },
    },
]
