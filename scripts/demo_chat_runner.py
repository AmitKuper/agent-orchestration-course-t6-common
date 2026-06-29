"""Chat turn and demo run helpers for demo_chat.py."""

from __future__ import annotations

import asyncio
import json
import os

from fastmcp import Client


async def _chat_turn(
    client: Client,
    caller: object,
    conversation: list[dict],
    user_message: str,
) -> str:
    """Send one user message; LLM may call server tools or just reply.

    Args:
        client: FastMCP Client connected to the server.
        caller: ToolCaller driving the LLM loop.
        conversation: Running message history (mutated in-place).
        user_message: What the human says.

    Returns:
        The assistant's final text reply.
    """
    from game.wrappers.mcp_agent_tools import GAME_TOOLS

    conversation.append({"role": "user", "content": user_message})
    print(f"\n[YOU]  {user_message}")
    tool_calls_made: list[str] = []
    last_text = ""

    async def executor(name: str, args: dict) -> str:
        """Execute a tool call and log it."""
        tool_calls_made.append(name)
        print(f"       >> server tool call: {name}({json.dumps(args, indent=None)[:80]})")
        result = await client.call_tool(name, args)
        text = result.content[0].text if result.content else "{}"
        print(f"       << server reply:     {text[:120]}")
        return text

    result_messages = await caller.call_with_tools(
        list(conversation), GAME_TOOLS, executor,
        system=(
            "You are having a friendly chat with a human who wants to play "
            "Cop & Thief on a 5×5 grid. You also have access to game tools "
            "(get_state, take_action, get_actor_action). Use tools when the "
            "human wants to actually play; reply conversationally otherwise. "
            "For game moves, pick game_id='demo01' and actor='thief'."
        ),
    )
    for msg in reversed(result_messages):
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
    if not tool_calls_made:
        print("       (no tools called — server was never contacted)")
    print(f"\n[BOT]  {last_text}")
    conversation.append({"role": "assistant", "content": last_text})
    return last_text


async def run_demo(url: str, api_key: str) -> None:
    """List server capabilities, then run a multi-turn conversation.

    Args:
        url: MCP server base URL.
        api_key: Bearer token for authentication.
    """
    from fastmcp.client.auth.bearer import BearerAuth

    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    auth = BearerAuth(api_key)
    async with Client(url + "/mcp", auth=auth) as client:
        print(f"\n{'='*60}\n  1. SERVER CAPABILITIES\n{'='*60}")
        tools = await client.list_tools()
        prompts = await client.list_prompts()
        resources = await client.list_resources()
        print("\nTools:", [t.name for t in tools])
        print("Prompts:", [p.name for p in prompts])
        print("Resources:", [r.uri for r in resources])

        print(f"\n{'='*60}\n  2. CREATE GAME\n{'='*60}")
        result = await client.call_tool("new_game_tool", {
            "game_id": "demo01", "cop_col": 0, "cop_row": 0,
            "thief_col": 4, "thief_row": 4, "seed": 42,
        })
        print(result.content[0].text if result.content else "no response")

        print(f"\n{'='*60}\n  3. MULTI-TURN CHAT\n{'='*60}")
        gk = Gatekeeper(model=os.environ.get("LLM_MODEL") or None)
        caller = ToolCaller(gk)
        history: list[dict] = []
        for utterance in [
            "Hey! How was your day?",
            "Awesome. Want to play a quick game of Cop and Thief?",
            "Great! I'm the thief. What does the board look like right now?",
            "OK I'll move north.",
            "What are my options now? Am I close to being caught?",
            "Ha, this is fun! Thanks for playing with me.",
        ]:
            await _chat_turn(client, caller, history, utterance)
            await asyncio.sleep(0.3)
