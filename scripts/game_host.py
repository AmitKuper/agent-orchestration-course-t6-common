"""Interactive game host: human types anything, LLM translates to MCP tools.

The server exposes Prompts (rules) and Resources (config) at startup.
The client loads them into the LLM's system prompt so it can answer rule
questions and make moves — all through natural language.

Usage:
    python scripts/game_host.py [--game-id demo01] [--role thief|cop]
    Type anything. Type 'quit' to exit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(_REPO_ROOT / ".env")
_API_KEY = os.environ.get("MCP_API_KEY", "demo-key")
_URL = "http://localhost:8001"


def _wait_for_server(timeout: float = 15.0) -> None:
    """Poll health endpoint until the server is ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(_URL + "/health", timeout=2.0).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError("Server did not start in time")


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
        m.content.text for m in prompt_result.messages
        if hasattr(m.content, "text")
    )

    cfg_result = await client.read_resource("game://config")
    cfg_text = cfg_result[0].text if cfg_result else "{}"
    cfg = json.loads(cfg_text)

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
        "- When the human asks about the board or their position, call get_state.\n"
        "- Always describe the result of a move in human terms "
        "(direction, new position, whether they're close to the cop/thief).\n"
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
    tool_calls_made: list[str] = []
    last_text = ""

    async def executor(name: str, args: dict) -> str:
        """Execute a tool call on the MCP server."""
        tool_calls_made.append(name)
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


async def run_host(game_id: str, role: str) -> None:
    """Start the game, load server context, then drop into the conversation loop."""
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    auth = BearerAuth(_API_KEY)

    async with Client(_URL + "/mcp", auth=auth) as client:
        # Create the game
        await client.call_tool("new_game_tool", {
            "game_id": game_id, "cop_col": 0, "cop_row": 0,
            "thief_col": 4, "thief_row": 4, "seed": 42,
        })

        # Build system prompt from server's Prompts + Resources
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


async def main(game_id: str, role: str) -> None:
    """Launch MCP server subprocess, wait for it, run the host loop."""
    env = {**os.environ, "MCP_ALLOWED_API_KEYS": _API_KEY, "MCP_API_KEY": _API_KEY}
    proc = subprocess.Popen(
        [sys.executable, "-m", "game.wrappers.mcp_server",
         "--port", "8001", "--games-dir", "games/host_demo"],
        env=env, cwd=str(_REPO_ROOT), stderr=subprocess.DEVNULL,
    )
    try:
        print("Starting MCP server...", end=" ", flush=True)
        _wait_for_server()
        print("ready!\n")
        await run_host(game_id, role)
    finally:
        proc.terminate()
        proc.wait()
        print("[server stopped]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", default="demo01")
    parser.add_argument("--role", choices=["thief", "cop"], default="thief")
    args = parser.parse_args()
    asyncio.run(main(args.game_id, args.role))
