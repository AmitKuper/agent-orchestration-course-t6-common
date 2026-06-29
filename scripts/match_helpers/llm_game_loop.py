"""LLM-mode game loop: LLM calls get_state then take_action each turn."""

from __future__ import annotations

import json
import os

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

from match_helpers import API_KEY
from match_helpers.actor_turn import _SYSTEM_COP, _SYSTEM_THIEF, _tech_loss


async def _agent_turn(
    caller: object, client: Client, game_id: str, actor: str, system: str,
) -> dict:
    """Run one LLM tool-use turn: the model calls get_state then take_action.

    Args:
        caller: ToolCaller instance driving the LLM loop.
        client: FastMCP Client connected to the relevant server.
        game_id: Active game identifier.
        actor: "cop" or "thief".
        system: System prompt grounding the agent in its role.

    Returns:
        Parsed ActionResult dict from the take_action tool call.
    """
    from game.wrappers.mcp_agent_tools import GAME_TOOLS

    last_result: dict = {}

    async def executor(name: str, args: dict) -> str:
        """Execute a tool call via the MCP client and capture take_action results."""
        nonlocal last_result
        tool_result = await client.call_tool(name, args)
        text = tool_result.content[0].text if tool_result.content else "{}"
        if name == "take_action":
            last_result = json.loads(text)
        return text

    prompt = (
        f"Take your turn as {actor} in game {game_id}. "
        "First call get_state to see the board, then call take_action with your move."
    )
    await caller.call_with_tools(
        [{"role": "user", "content": prompt}], GAME_TOOLS, executor, system=system,
    )
    return last_result


async def _game_loop(
    url_a: str, url_b: str, game_id: str, max_rounds: int,
) -> dict:
    """Drive alternating thief/cop turns until game_over or max_rounds (LLM mode).

    Args:
        url_a: URL of the thief server.
        url_b: URL of the cop server.
        game_id: Active game identifier.
        max_rounds: Maximum rounds before the orchestrator cuts off.

    Returns:
        Final ActionResult dict, or a technical-loss sentinel on divergence.
    """
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    model = os.environ.get("LLM_MODEL") or None
    caller = ToolCaller(Gatekeeper(model=model))
    auth = BearerAuth(API_KEY)
    last_result: dict = {}
    async with Client(url_a + "/mcp", auth=auth, timeout=30.0) as ca, \
               Client(url_b + "/mcp", auth=auth, timeout=30.0) as cb:
        game_over, round_num = False, 0
        while not game_over and round_num < max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for client, actor, system in [
                (ca, "thief", _SYSTEM_THIEF), (cb, "cop", _SYSTEM_COP),
            ]:
                result = await _agent_turn(caller, client, game_id, actor, system)
                if result.get("hash_match") is False:
                    return _tech_loss("hash_mismatch")
                if "comm_error" in result:
                    return _tech_loss(f"comm_error:{result['comm_error']}")
                last_result = result
                print(f"  {actor}: {result}")
                if result.get("game_over"):
                    game_over = True
                    break
    return last_result
