"""System-prompt builder, turn executor, and host loop for game_host.py."""

from __future__ import annotations

import json
import os

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth


async def _build_system_prompt(client: Client, role: str, game_id: str) -> str:
    """Pull rules + config from the server and compose the LLM system prompt.

    Args:
        client: Active FastMCP client connected to the server.
        role: "cop" or "thief" — which prompt to load.
        game_id: Current game identifier embedded in the prompt.

    Returns:
        System prompt string that grounds the LLM in game rules and context.
    """
    prompt_result = await client.get_prompt(f"{role}_rules", {"game_id": game_id})
    rules = "\n".join(
        m.content.text for m in prompt_result.messages if hasattr(m.content, "text")
    )
    cfg_result = await client.read_resource("game://config")
    cfg = json.loads(cfg_result[0].text if cfg_result else "{}")
    return (
        "You are a friendly, enthusiastic game host for Cop & Thief, a pursuit game "
        f"on a {cfg['grid_size'][0]}x{cfg['grid_size'][1]} grid. "
        f"The human is playing as the {role.upper()}. "
        f"The active game ID is '{game_id}'.\n\n"
        "=== GAME RULES (loaded from the MCP server) ===\n"
        f"{rules}\n\n"
        "=== CONFIG ===\n"
        f"Max rounds: {cfg['max_moves']}  |  Max barriers: {cfg['max_barriers']}  |  "
        f"Partial observation radius: {cfg['view_radius']}\n\n"
        "=== YOUR BEHAVIOUR ===\n"
        "- Answer questions about the rules in friendly, plain English.\n"
        "- When the human wants to make a move, call take_action (actor='{role}', "
        f"game_id='{game_id}').\n"
        "- When the human asks about the board or position, call get_state.\n"
        "- Always describe the result of a move in human terms.\n"
        "- Be concise but warm. Never show raw JSON to the user.\n"
        "- If a move fails, explain why in plain language.\n"
        f"actor_param='{role}' game_id_param='{game_id}'"
    )


async def _one_turn(
    caller: object,
    client: Client,
    history: list[dict],
    system: str,
    user_text: str,
) -> str:
    """Send one user message through the LLM; call server tools as needed.

    Args:
        caller: ToolCaller driving the LLM loop.
        client: FastMCP client for tool execution.
        history: Running message history (mutated in-place).
        system: System prompt grounding the LLM.
        user_text: What the human typed.

    Returns:
        Assistant's natural-language reply.
    """
    from game.wrappers.mcp_agent_tools import GAME_TOOLS

    history.append({"role": "user", "content": user_text})
    last_text = ""

    async def executor(name: str, args: dict) -> str:
        """Execute a tool call on the MCP server."""
        print(f"  [calling {name}...]", flush=True)
        result = await client.call_tool(name, args)
        return result.content[0].text if result.content else "{}"

    result_msgs = await caller.call_with_tools(
        list(history), GAME_TOOLS, executor, system=system,
    )
    for msg in reversed(result_msgs):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_text = content
                break
            if isinstance(content, list):
                texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                if texts:
                    last_text = texts[-1]
                    break
    history.append({"role": "assistant", "content": last_text})
    return last_text


async def run_host(url: str, api_key: str, game_id: str, role: str) -> None:
    """Create game, build system prompt, then run the interactive host loop.

    Args:
        url: MCP server base URL.
        api_key: Bearer token for authentication.
        game_id: Identifier for the game session.
        role: "cop" or "thief".
    """
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    auth = BearerAuth(api_key)
    async with Client(url + "/mcp", auth=auth) as client:
        await client.call_tool("new_game_tool", {
            "game_id": game_id, "cop_col": 0, "cop_row": 0,
            "thief_col": 4, "thief_row": 4, "seed": 42,
        })
        system = await _build_system_prompt(client, role, game_id)
        gk = Gatekeeper(model=os.environ.get("LLM_MODEL") or None)
        caller = ToolCaller(gk)
        history: list[dict] = []
        print(f"\nGame '{game_id}' ready. You are the {role.upper()}.")
        print("Type anything — ask about rules, make moves, or just chat.")
        print("Type 'quit' to exit.\n")
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                print("Host: Thanks for playing! Goodbye.")
                break
            reply = await _one_turn(caller, client, history, system, user_input)
            print(f"\nHost: {reply}\n")
