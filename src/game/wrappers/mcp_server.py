"""MCP server entry point — assembles tools, prompts, resources, and REST routes.

Run with:
    python -m game.wrappers.mcp_server --port 8001 --games-dir games/server_a
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from fastmcp import FastMCP

from game.sdk.sdk import new_game as sdk_new_game
from game.wrappers.mcp_agent_tools import register_agent_tools
from game.wrappers.mcp_match_tools import register_match_tools
from game.wrappers.mcp_prompts import register_prompts
from game.wrappers.mcp_report_tool import register_report_tool
from game.wrappers.mcp_resources import register_resources
from game.wrappers.mcp_routes import register_routes
from game.wrappers.mcp_state import games_base, patch_state_game_id, server_state
from game.wrappers.mcp_sync_tools import register_sync_tools

mcp = FastMCP(
    name="cop-thief-game",
    instructions="Cop & Thief game engine. Use get_state then take_action to play.",
)
register_routes(mcp)
register_agent_tools(mcp)
register_sync_tools(mcp)
register_match_tools(mcp)
register_prompts(mcp)
register_resources(mcp)
register_report_tool(mcp)


@mcp.tool()
def new_game_tool(
    game_id: str, cop_col: int, cop_row: int,
    thief_col: int, thief_row: int, seed: int,
) -> str:
    """Create a new game with pre-agreed positions (called after match setup).

    Args:
        game_id: The agreed game identifier (also becomes the directory name).
        cop_col: Cop starting column.
        cop_row: Cop starting row.
        thief_col: Thief starting column.
        thief_row: Thief starting row.
        seed: Shared random seed recorded in the game log.

    Returns:
        JSON with "game_id" key, or {"error": ...} on failure.
    """
    try:
        result = sdk_new_game(
            grid_size=(5, 5),
            cop_pos=(cop_col, cop_row),
            thief_pos=(thief_col, thief_row),
            seed=seed,
            games_base=games_base(),
        )
        auto_id = result["game_id"]
        if auto_id != game_id:
            src = games_base() / auto_id
            if src.exists():
                shutil.move(str(src), str(games_base() / game_id))
        patch_state_game_id(game_id)
        return json.dumps({"game_id": game_id})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def main() -> None:
    """Parse CLI args and start the MCP HTTP server."""
    parser = argparse.ArgumentParser(description="Cop & Thief MCP server")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--games-dir", default="games")
    args = parser.parse_args()
    server_state["games_base"] = Path(args.games_dir)
    server_state["games_base"].mkdir(parents=True, exist_ok=True)
    server_state["port"] = args.port
    mcp.run(transport="streamable-http", host=args.host, port=args.port, json_response=True)


if __name__ == "__main__":
    main()
