"""MCP agent-facing game tools — get_state and take_action.

These tools are intended for use by the LLM orchestrator (run_match.py) in a
tool-use loop. The LLM calls get_state to observe the board, then take_action
to submit its chosen move. The server forwards the action to the opponent and
validates state hashes — the LLM never talks to the opponent directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from game.wrappers.actor_loader import load_actor_backend

if TYPE_CHECKING:
    from fastmcp import FastMCP

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
            "Valid actions: N NE E SE S SW W NW (movement) or BARRIER "
            "(cop only, places barrier on current cell). "
            "Include a short natural-language message describing your intent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "string", "description": "The game identifier."},
                "actor": {"type": "string", "description": "'cop' or 'thief'."},
                "action": {"type": "string", "description": "Move direction or BARRIER."},
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


def register_agent_tools(mcp: FastMCP) -> None:
    """Register get_state and take_action MCP tools on the given server.

    The LLM client drives the turn loop — it calls get_state to observe the
    board and take_action to submit a move.  The server applies the action,
    forwards it to the opponent, and validates state hashes.

    Args:
        mcp: The FastMCP server instance to attach tools to.
    """
    @mcp.tool()
    def get_state(game_id: str, actor: str) -> str:
        """Return the current ObservationState as JSON.

        Args:
            game_id: The active game identifier.
            actor: "cop" or "thief".

        Returns:
            JSON ObservationState including position, legal moves, and barriers.
        """
        from game.sdk.sdk import get_state as sdk_get_state
        from game.wrappers.mcp_state import games_base

        try:
            obs = sdk_get_state(game_id, actor, games_base())
            return json.dumps(asdict(obs))
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def take_action(game_id: str, actor: str, action: str, message: str = "") -> str:
        """Submit an action, forward it to the opponent, and validate state hashes.

        Args:
            game_id: The active game identifier.
            actor: "cop" or "thief".
            action: Move direction or BARRIER.
            message: Natural-language intent message (optional).

        Returns:
            JSON ActionResult extended with hash_match boolean.
        """
        from game.sdk.sdk import state_hash as sdk_hash
        from game.sdk.sdk import submit_action as sdk_submit_action
        from game.wrappers.mcp_client import fetch_hash, send_receive_action
        from game.wrappers.mcp_state import games_base

        try:
            result = sdk_submit_action(
                game_id, actor, action, message=message, games_base=games_base()
            )
            response = asdict(result)
            if result.success:
                try:
                    send_receive_action(game_id, actor, action, message)
                    local_h = sdk_hash(game_id, games_base())
                    opp_h = fetch_hash(game_id)
                    response["hash_match"] = local_h == opp_h
                except Exception as comm_err:
                    response["comm_error"] = str(comm_err)
            return json.dumps(response)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def get_actor_action(game_id: str, actor: str) -> str:
        """Return the actor backend's action recommendation without applying it.

        Args:
            game_id: The active game identifier.
            actor: "cop" or "thief".

        Returns:
            JSON with "action" and "legal_moves" keys, or {"error": ...} on failure.
        """
        from game.sdk.sdk import get_state as sdk_get_state
        from game.wrappers.mcp_state import games_base
        try:
            obs = sdk_get_state(game_id, actor, games_base())
            action = load_actor_backend(actor).get_action(obs)
            return json.dumps({"action": action, "legal_moves": obs.legal_moves})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
