"""Orchestrate a full game between two local MCP servers.

Usage:
    python scripts/run_match.py [--seed SEED] [--max-rounds 30]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).parent.parent
_API_KEY = os.environ.get("MCP_API_KEY", "demo-key")
_HEADERS = {"X-API-Key": _API_KEY}


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    """Poll the health endpoint until the server responds or timeout."""
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
    """POST JSON to a server REST endpoint and return parsed response."""
    r = httpx.post(url + path, json=body, headers=_HEADERS, timeout=30.0)
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


def _mcp_call(tool_name: str, arguments: dict) -> dict:
    """Build a FastMCP streamable-HTTP tool-call request body."""
    return {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }


def _parse_tool_result(resp: dict) -> dict:
    """Extract the tool result content from an MCP JSON-RPC response."""
    try:
        return json.loads(resp["result"]["content"][0]["text"])
    except Exception:
        return resp


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


def main() -> None:
    """Run a match between two local servers and print the log path."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=random.randint(0, 9999))
    parser.add_argument("--max-rounds", type=int, default=30)
    args = parser.parse_args()

    seed = args.seed
    grid = (5, 5)
    cop_pos, thief_pos = _derive_positions(seed, grid)
    game_id = f"match{seed:04d}"
    print(f"[match] seed={seed} game_id={game_id} cop={cop_pos} thief={thief_pos}")

    env_a = {**os.environ, "OPPONENT_MCP_URL": "http://localhost:8002",
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY}
    env_b = {**os.environ, "OPPONENT_MCP_URL": "http://localhost:8001",
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY}
    python = str(_REPO_ROOT / ".venv" /
                 ("Scripts" if sys.platform == "win32" else "bin") /
                 ("python.exe" if sys.platform == "win32" else "python"))

    proc_a, proc_b = _start_servers(env_a, env_b, python)
    url_a, url_b = "http://localhost:8001", "http://localhost:8002"

    try:
        print("[match] waiting for servers…")
        _wait_for_server(url_a)
        _wait_for_server(url_b)
        print("[match] both servers up")

        proposal = {"game_id": game_id, "seed": seed,
                    "cop_pos": cop_pos, "thief_pos": thief_pos,
                    "grid_size": list(grid), "my_role": "cop"}
        resp_b = _post(url_b, "/game/propose_match", proposal)
        print(f"[match] B accepted: {resp_b}")
        _post(url_a, "/game/propose_match", {**proposal, "my_role": "thief"})

        game_over, round_num = False, 0
        while not game_over and round_num < args.max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for server_url, actor in [(url_a, "thief"), (url_b, "cop")]:
                resp = _post(server_url, "/mcp",
                             _mcp_call("take_turn", {"game_id": game_id, "actor": actor}))
                result = _parse_tool_result(resp)
                print(f"  {actor}: {result}")
                if result.get("game_over"):
                    game_over = True
                    break

        log_a = Path("games/server_a") / game_id / "game.log"
        log_b = Path("games/server_b") / game_id / "game.log"
        print(f"\n[match] done. Logs:\n  {log_a}\n  {log_b}")
    finally:
        proc_a.terminate()
        proc_b.terminate()
        proc_a.wait()
        proc_b.wait()
        print("[match] servers stopped")


if __name__ == "__main__":
    main()
