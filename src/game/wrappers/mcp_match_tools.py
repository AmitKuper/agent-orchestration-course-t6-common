"""MCP tool to self-initiate a match against an external opponent server.

The server calls run_match.py as a subprocess, passing --local-url so the
orchestrator attaches to this already-running server instead of spawning a new one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

_RUN_MATCH = Path(__file__).resolve().parents[4] / "scripts" / "run_match.py"


def register_match_tools(mcp: FastMCP) -> None:
    """Register start_match tool on the MCP server.

    Args:
        mcp: The FastMCP server instance to attach tools to.
    """

    @mcp.tool()
    def start_match(
        opponent_url: str,
        seed: int = -1,
        num_games: int = 0,
        mode: str = "actor",
    ) -> str:
        """Initiate a match series against an external opponent MCP server.

        Spawns the run_match.py orchestrator in the background, pointing at
        this server (via --local-url) and the given opponent.  Returns
        immediately; the match runs asynchronously.

        Args:
            opponent_url: Base URL of opponent's MCP server (e.g. 51.4.97.97:80).
            seed: Random seed (-1 = random, chosen by orchestrator).
            num_games: Sub-games to play (0 = use config.json default).
            mode: "actor" for Q-table actor, "llm" for LLM agent.

        Returns:
            JSON {"started": true, "pid": <pid>, "opponent_url": ..., "local_url": ...}.
        """
        from game.wrappers.mcp_state import server_state

        port = server_state.get("port", 8001)
        local_url = f"http://localhost:{port}"
        cmd = [
            sys.executable, str(_RUN_MATCH),
            "--local-url", local_url,
            "--opponent-url", opponent_url,
            "--mode", mode,
        ]
        if seed >= 0:
            cmd += ["--seed", str(seed)]
        if num_games > 0:
            cmd += ["--num-games", str(num_games)]

        proc = subprocess.Popen(cmd, cwd=str(_RUN_MATCH.parent.parent))
        return json.dumps({
            "started": True,
            "pid": proc.pid,
            "opponent_url": opponent_url,
            "local_url": local_url,
        })
