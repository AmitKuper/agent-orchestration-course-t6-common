"""Orchestrate a full game between two local MCP servers using LLM tool-use.

The LLM lives in this orchestrator, not inside the servers.  For each turn the
orchestrator calls ToolCaller.call_with_tools; the LLM calls get_state then
take_action via the MCP client until the game ends.

Usage:
    python scripts/run_match.py [--seed SEED] [--max-rounds 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

_REPO_ROOT = Path(__file__).parent.parent
_API_KEY = os.environ.get("MCP_API_KEY", "demo-key")

_SYSTEM_COP = (
    "You are the COP in a 5×5 Cop & Thief grid game. "
    "Capture the thief by landing on its cell. "
    "You may move N NE E SE S SW W NW or place BARRIER on your cell (max 5). "
    "Call get_state to observe the board, then take_action with your move and a brief message."
)
_SYSTEM_THIEF = (
    "You are the THIEF in a 5×5 Cop & Thief grid game. "
    "Survive 25 rounds without being captured. "
    "You may move N NE E SE S SW W NW. No barriers. "
    "Call get_state to observe the board, then take_action with your move and a brief message."
)


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    """Poll the health endpoint until the server responds or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url + "/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not start within {timeout}s")


def _post(url: str, path: str, body: dict) -> dict:
    """POST JSON to a REST endpoint and return parsed response."""
    r = httpx.post(url + path, json=body,
                   headers={"X-API-Key": _API_KEY}, timeout=30.0)
    r.raise_for_status()
    return r.json()


def _derive_positions(seed: int, grid: tuple[int, int]) -> tuple[list[int], list[int]]:
    """Derive cop and thief start positions deterministically from seed."""
    rng = random.Random(seed)
    cols, rows = grid
    cop = [rng.randrange(cols), rng.randrange(rows)]
    thief = cop[:]
    while thief == cop:
        thief = [rng.randrange(cols), rng.randrange(rows)]
    return cop, thief


def _start_servers(env_a: dict, env_b: dict, python: str) -> tuple:
    """Launch server A (port 8001) and server B (port 8002) as subprocesses."""
    mod = "game.wrappers.mcp_server"
    cwd = str(_REPO_ROOT)
    proc_a = subprocess.Popen(
        [python, "-m", mod, "--port", "8001", "--games-dir", "games/server_a"],
        env=env_a, cwd=cwd,
    )
    proc_b = subprocess.Popen(
        [python, "-m", mod, "--port", "8002", "--games-dir", "games/server_b"],
        env=env_b, cwd=cwd,
    )
    return proc_a, proc_b


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
        [{"role": "user", "content": prompt}],
        GAME_TOOLS,
        executor,
        system=system,
    )
    return last_result


async def _game_loop(
    url_a: str, url_b: str, game_id: str, max_rounds: int,
) -> None:
    """Drive alternating thief/cop turns until game_over or max_rounds."""
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    model = os.environ.get("LLM_MODEL") or None
    caller = ToolCaller(Gatekeeper(model=model))

    auth = BearerAuth(_API_KEY)
    async with Client(url_a + "/mcp", auth=auth) as ca, \
               Client(url_b + "/mcp", auth=auth) as cb:
        game_over, round_num = False, 0
        while not game_over and round_num < max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for client, actor, system in [
                (ca, "thief", _SYSTEM_THIEF),
                (cb, "cop", _SYSTEM_COP),
            ]:
                result = await _agent_turn(caller, client, game_id, actor, system)
                print(f"  {actor}: {result}")
                if result.get("game_over"):
                    game_over = True
                    break


async def _async_main(seed: int, max_rounds: int) -> None:
    """Start servers, propose match, run LLM tool-use game loop, stop servers."""
    grid = (5, 5)
    cop_pos, thief_pos = _derive_positions(seed, grid)
    game_id = f"match{seed:04d}"
    print(f"[match] seed={seed} game_id={game_id} cop={cop_pos} thief={thief_pos}")

    env_a = {**os.environ, "OPPONENT_MCP_URL": "http://localhost:8002",
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY}
    env_b = {**os.environ, "OPPONENT_MCP_URL": "http://localhost:8001",
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY}

    proc_a, proc_b = _start_servers(env_a, env_b, sys.executable)
    url_a, url_b = "http://localhost:8001", "http://localhost:8002"
    try:
        print("[match] waiting for servers…")
        _wait_for_server(url_a)
        _wait_for_server(url_b)
        print("[match] both servers up")

        proposal = {"game_id": game_id, "seed": seed,
                    "cop_pos": cop_pos, "thief_pos": thief_pos,
                    "grid_size": list(grid), "my_role": "cop"}
        _post(url_b, "/game/propose_match", proposal)
        _post(url_a, "/game/propose_match", {**proposal, "my_role": "thief"})

        await _game_loop(url_a, url_b, game_id, max_rounds)

        log_a = Path("games/server_a") / game_id / "game.log"
        log_b = Path("games/server_b") / game_id / "game.log"
        print(f"\n[match] done. Logs:\n  {log_a}\n  {log_b}")
    finally:
        proc_a.terminate()
        proc_b.terminate()
        proc_a.wait()
        proc_b.wait()
        print("[match] servers stopped")


def main() -> None:
    """Parse CLI args and run the async match orchestrator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=random.randint(0, 9999))
    parser.add_argument("--max-rounds", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(_async_main(args.seed, args.max_rounds))


if __name__ == "__main__":
    main()
