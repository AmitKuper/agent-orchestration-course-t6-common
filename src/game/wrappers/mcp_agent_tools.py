"""MCP agent-facing game tools — get_state, take_action, get_actor_action.

Tool schemas live in mcp_game_tool_schemas.py.
Opponent MCP call logic lives in mcp_opponent_caller.py.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from game.wrappers.actor_loader import load_actor_backend
from game.wrappers.mcp_game_tool_schemas import GAME_TOOLS
from game.wrappers.mcp_opponent_caller import call_opponent

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = ["GAME_TOOLS", "register_agent_tools"]


def register_agent_tools(mcp: FastMCP) -> None:
    """Register get_state, take_action, and get_actor_action on the MCP server.

    Args:
        mcp: The FastMCP server instance to attach tools to.
    """
    @mcp.tool()
    def get_state(game_id: str, actor: str) -> str:
        """Return the current ObservationState as JSON.

        Includes opponent_last_message so LLM agents can reason from
        the opponent's natural-language intent, not just grid positions.

        Args:
            game_id: The active game identifier.
            actor: "cop" or "thief".

        Returns:
            JSON ObservationState including position, legal moves, barriers,
            and the opponent's last natural-language message.
        """
        import dataclasses

        from game.sdk.sdk import get_state as sdk_get_state
        from game.wrappers.mcp_message_store import get_opponent_message
        from game.wrappers.mcp_state import games_base

        try:
            obs = sdk_get_state(game_id, actor, games_base())
            opp_msg = get_opponent_message(game_id, actor)
            if opp_msg:
                obs = dataclasses.replace(obs, opponent_last_message=opp_msg)
            return json.dumps(asdict(obs))
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def take_action(game_id: str, actor: str, action: str, message: str = "") -> str:
        """Submit an action, forward it via MCP to the opponent, validate hashes.

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
        from game.wrappers.mcp_state import games_base, server_state

        try:
            result = sdk_submit_action(
                game_id, actor, action, message=message, games_base=games_base()
            )
            if message:
                from game.wrappers.mcp_message_store import record_message
                record_message(game_id, actor, message)
            response = asdict(result)
            if result.success:
                match_meta = server_state.get("matches", {}).get(game_id, {})
                opp_url = (
                    match_meta.get("opponent_url")
                    or os.environ.get("OPPONENT_MCP_URL", "")
                ).rstrip("/")
                if opp_url:
                    opp_h, err = await call_opponent(
                        opp_url, os.environ.get("MCP_API_KEY", ""),
                        game_id, actor, action, message or "",
                    )
                    if err:
                        response["comm_error"] = err
                    else:
                        local_h = sdk_hash(game_id, games_base())
                        response["hash_match"] = local_h == opp_h
                else:
                    response["comm_error"] = "OPPONENT_MCP_URL not set"
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
