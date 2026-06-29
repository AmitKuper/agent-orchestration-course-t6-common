"""Demo: start one MCP server and "talk" to it like a person.

Shows what the server CAN and CANNOT respond to:
- Conversational requests ("how was your day?") have no tool → LLM handles them alone
- Game requests ("want to play?", "move north") → LLM calls server tools

Usage:
    python scripts/demo_chat.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

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


async def main() -> None:
    """Start server, run demo, stop server."""
    from demo_chat_runner import run_demo

    env = {**os.environ, "MCP_ALLOWED_API_KEYS": _API_KEY, "MCP_API_KEY": _API_KEY}
    proc = subprocess.Popen(
        [sys.executable, "-m", "game.wrappers.mcp_server",
         "--port", "8001", "--games-dir", "games/demo"],
        env=env, cwd=str(_REPO_ROOT),
    )
    try:
        print("Starting server...", end=" ", flush=True)
        _wait_for_server()
        print("up!")
        await run_demo(_URL, _API_KEY)
    finally:
        proc.terminate()
        proc.wait()
        print("\n[server stopped]")


if __name__ == "__main__":
    asyncio.run(main())
