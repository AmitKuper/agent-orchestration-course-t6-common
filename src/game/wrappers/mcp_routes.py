"""Custom REST route handlers for server-to-server communication.

Registered on the FastMCP instance via register_routes(mcp) to avoid
circular imports between mcp_server and its route handlers.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse

from game.sdk.sdk import new_game as sdk_new_game
from game.sdk.sdk import state_hash as sdk_hash
from game.sdk.sdk import submit_action as sdk_submit_action
from game.wrappers.mcp_state import auth_ok, games_base, server_state

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_routes(mcp: FastMCP) -> None:
    """Register all custom HTTP routes on the FastMCP instance.

    Args:
        mcp: The FastMCP server instance to attach routes to.
    """
    @mcp.custom_route("/game/receive_action", methods=["POST"])
    async def receive_action(request: Request) -> JSONResponse:
        """Inbound: apply the opponent's action to the local engine."""
        if not auth_ok(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        data = await request.json()
        result = sdk_submit_action(
            data["game_id"], data["actor"], data["action"],
            message=data.get("message"), games_base=games_base(),
        )
        return JSONResponse({**asdict(result), "hash": sdk_hash(data["game_id"], games_base())})

    @mcp.custom_route("/game/hash", methods=["POST"])
    async def get_hash(request: Request) -> JSONResponse:
        """Return the local state hash for the given game."""
        if not auth_ok(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        data = await request.json()
        return JSONResponse({"hash": sdk_hash(data["game_id"], games_base())})

    @mcp.custom_route("/game/propose_match", methods=["POST"])
    async def propose_match(request: Request) -> JSONResponse:
        """Accept a match proposal and create a local game with agreed params."""
        if not auth_ok(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        data = await request.json()
        game_id = data["game_id"]
        result = sdk_new_game(
            grid_size=tuple(data.get("grid_size", [5, 5])),
            cop_pos=tuple(data["cop_pos"]),
            thief_pos=tuple(data["thief_pos"]),
            seed=data["seed"],
            games_base=games_base(),
        )
        auto_id = result["game_id"]
        if auto_id != game_id and (games_base() / auto_id).exists():
            shutil.move(str(games_base() / auto_id), str(games_base() / game_id))
        server_state["matches"][game_id] = {
            "role": data.get("my_role", "cop"), "seed": data["seed"],
        }
        return JSONResponse({"accepted": True, "game_id": game_id})

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse({"status": "ok"})
