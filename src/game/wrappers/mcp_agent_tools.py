"""MCP agent-facing game tools — get_state, take_action, get_actor_action."""

from __future__ import annotations

import asyncio
import json
import os
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


_OPP_TIMEOUT = 30.0  # seconds; avoids hung TCP connections to unresponsive opponents
_RECV_RETRIES = 3    # retry attempts before declaring comm_error


async def _call_opponent(
    opp_url: str, api_key: str, game_id: str,
    actor: str, action: str, message: str,
) -> tuple[str | None, str | None]:
    """Forward action to opponent with per-call timeout and retry.

    Args:
        opp_url: Opponent MCP base URL (no trailing slash, no /mcp suffix).
        api_key: Bearer token for outbound requests.
        game_id: The active game identifier.
        actor: "cop" or "thief".
        action: Move direction or BARRIER.
        message: Natural-language intent message.

    Returns:
        (opp_hash, None) on success, (None, error_string) after all retries fail.
    """
    from fastmcp import Client
    from fastmcp.client.auth.bearer import BearerAuth

    auth = BearerAuth(api_key)
    last_err: str | None = None
    for attempt in range(_RECV_RETRIES):
        try:
            async with Client(opp_url + "/mcp", auth=auth, timeout=_OPP_TIMEOUT) as opp:
                recv = await opp.call_tool("receive_action", {
                    "game_id": game_id, "actor": actor,
                    "action": action, "message": message,
                })
                recv_data = json.loads(recv.content[0].text if recv.content else "{}")
                if "success" not in recv_data:
                    last_err = f"receive_action: {recv_data.get('error')}"
                    if attempt < _RECV_RETRIES - 1:
                        await asyncio.sleep(2.0)
                    continue
                hr = await opp.call_tool("get_hash", {"game_id": game_id})
                opp_h = json.loads(hr.content[0].text if hr.content else "{}").get("hash", "")
            return opp_h, None
        except Exception as exc:
            last_err = str(exc)
            if attempt < _RECV_RETRIES - 1:
                await asyncio.sleep(2.0)
    return None, last_err


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

        Uses the MCP protocol end-to-end: calls receive_action and get_hash
        tools on the opponent server via a FastMCP Client (not plain HTTP).

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
                    opp_h, err = await _call_opponent(
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
