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


async def main(game_id: str, role: str) -> None:
    """Launch MCP server subprocess, wait for it, run the host loop."""
    from game_host_runner import run_host

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
        await run_host(_URL, _API_KEY, game_id, role)
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
