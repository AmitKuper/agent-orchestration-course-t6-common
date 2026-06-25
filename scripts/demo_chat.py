"""Demo: start one MCP server and "talk" to it like a person.

Shows what the server CAN and CANNOT respond to:
- Conversational requests ("how was your day?") have no tool → LLM handles them alone
- Game requests ("want to play?", "move north") → LLM calls server tools

Usage:
    python scripts/demo_chat.py
"""

from __future__ import annotations

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
    """Poll health endpoint until server is up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(_URL + "/health", timeout=2.0).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError("Server did not start in time")


def _divider(label: str) -> None:
    """Print a section divider."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print("=" * 60)


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
        list(conversation),
        GAME_TOOLS,
        executor,
        system=(
            "You are having a friendly chat with a human who wants to play "
            "Cop & Thief on a 5×5 grid. You also have access to game tools "
            "(get_state, take_action, get_actor_action). Use tools when the "
            "human wants to actually play; reply conversationally otherwise. "
            "For game moves, pick game_id='demo01' and actor='thief'."
        ),
    )

    # Extract final assistant text from result_messages
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


async def run_demo() -> None:
    """Main demo: list server capabilities, then have a multi-turn conversation."""
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    auth = BearerAuth(_API_KEY)

    async with Client(_URL + "/mcp", auth=auth) as client:
        # ── 1. What does the server actually offer? ─────────────────────
        _divider("1. SERVER CAPABILITIES (what the MCP server exposes)")

        tools = await client.list_tools()
        prompts = await client.list_prompts()
        resources = await client.list_resources()

        print("\nTools (things the server can DO):")
        for t in tools:
            print(f"  • {t.name}: {t.description[:70] if t.description else ''}")

        print("\nPrompts (LLM grounding texts the server provides):")
        for p in prompts:
            print(f"  • {p.name}")

        print("\nResources (data the server publishes):")
        for r in resources:
            print(f"  • {r.uri}")

        # ── 2. Read the game://config resource ──────────────────────────
        _divider("2. READ game://config RESOURCE")
        cfg_result = await client.read_resource("game://config")
        cfg_text = cfg_result[0].text if cfg_result else "{}"
        print(f"\n{cfg_text}")

        # ── 3. Get a prompt ─────────────────────────────────────────────
        _divider("3. READ thief_rules PROMPT")
        prompt_result = await client.get_prompt("thief_rules", {"game_id": "demo01"})
        for msg in prompt_result.messages:
            print(f"\n{msg.content.text[:300]}")

        # ── 4. Create a game so tools work ──────────────────────────────
        _divider("4. CREATE GAME (direct tool call)")
        result = await client.call_tool("new_game_tool", {
            "game_id": "demo01",
            "cop_col": 0, "cop_row": 0,
            "thief_col": 4, "thief_row": 4,
            "seed": 42,
        })
        print(f"\n{result.content[0].text if result.content else 'no response'}")

        # ── 5. The conversation ──────────────────────────────────────────
        _divider("5. MULTI-TURN CHAT (LLM + tool-use loop)")
        print("\nNotice: the server only responds when the LLM calls a tool.")
        print("Conversational messages ('how was your day?') never reach the server.\n")

        gk = Gatekeeper(model=os.environ.get("LLM_MODEL") or None)
        caller = ToolCaller(gk)
        history: list[dict] = []

        for utterance in [
            "Hey! How was your day?",
            "Awesome. Want to play a quick game of Cop and Thief?",
            "Great! I'm the thief. What does the board look like right now?",
            "OK I'll move north.",
            "Interesting! What are my options now? Am I close to being caught?",
            "Ha, this is fun! Thanks for playing with me.",
        ]:
            await _chat_turn(client, caller, history, utterance)
            await asyncio.sleep(0.3)


async def main() -> None:
    """Start server, run demo, stop server."""
    env = {
        **os.environ,
        "MCP_ALLOWED_API_KEYS": _API_KEY,
        "MCP_API_KEY": _API_KEY,
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "game.wrappers.mcp_server",
         "--port", "8001", "--games-dir", "games/demo"],
        env=env, cwd=str(_REPO_ROOT),
    )
    try:
        print("Starting server...", end=" ", flush=True)
        _wait_for_server()
        print("up!")
        await run_demo()
    finally:
        proc.terminate()
        proc.wait()
        print("\n[server stopped]")


if __name__ == "__main__":
    asyncio.run(main())
