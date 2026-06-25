"""MCP tools for server-to-server synchronisation (real MCP, not REST).

These tools replace the old custom REST routes (/game/receive_action,
/game/hash, /game/propose_match).  Both servers expose them so each can
call the other via a standard FastMCP Client.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from typing import TYPE_CHECKING

from game.wrappers.mcp_state import games_base, patch_state_game_id, server_state

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_sync_tools(mcp: FastMCP) -> None:
    """Register receive_action, get_hash, and propose_match_tool on the server.

    Args:
        mcp: The FastMCP server instance to attach tools to.
    """
    @mcp.tool()
    def receive_action(
        game_id: str, actor: str, action: str, message: str = "",
    ) -> str:
        """Apply the opponent's action to the local game engine.

        Called by the opponent server after it has submitted its own action,
        so both engines stay in sync.

        Args:
            game_id: The active game identifier.
            actor: "cop" or "thief" — the acting side.
            action: Move direction or BARRIER.
            message: Natural-language intent message (optional).

        Returns:
            JSON ActionResult dict, or {"error": ...} on failure.
        """
        from game.sdk.sdk import submit_action as sdk_submit_action
        from game.wrappers.mcp_message_store import record_message
        try:
            result = sdk_submit_action(
                game_id, actor, action,
                message=message or None, games_base=games_base(),
            )
            if message:
                record_message(game_id, actor, message)
            return json.dumps(asdict(result))
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def get_hash(game_id: str) -> str:
        """Return the local canonical state hash for cross-engine validation.

        Args:
            game_id: The active game identifier.

        Returns:
            JSON {"hash": "<8-char hex>"}, or {"error": ...} on failure.
        """
        from game.sdk.sdk import state_hash as sdk_hash
        try:
            return json.dumps({"hash": sdk_hash(game_id, games_base())})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def propose_match_tool(
        game_id: str, seed: int,
        cop_pos: list[int], thief_pos: list[int],
        grid_size: list[int], my_role: str,
        view_radius: int = 1,
    ) -> str:
        """Accept a match proposal and create a local game with agreed parameters.

        Replaces the old /game/propose_match REST route.

        Args:
            game_id: The agreed game identifier.
            seed: Shared random seed for deterministic start positions.
            cop_pos: [col, row] starting position for the cop.
            thief_pos: [col, row] starting position for the thief.
            grid_size: [cols, rows] grid dimensions.
            my_role: "cop" or "thief" — this server's role in the match.
            view_radius: Chebyshev distance within which opponent is visible.

        Returns:
            JSON {"accepted": True, "game_id": ...}, or {"error": ...}.
        """
        from game.sdk.sdk import new_game as sdk_new_game
        try:
            dest = games_base() / game_id
            if dest.exists():
                shutil.rmtree(str(dest))
            result = sdk_new_game(
                grid_size=tuple(grid_size),
                cop_pos=tuple(cop_pos),
                thief_pos=tuple(thief_pos),
                seed=seed,
                mechanics={"view_radius": view_radius},
                games_base=games_base(),
            )
            auto_id = result["game_id"]
            if auto_id != game_id and (games_base() / auto_id).exists():
                shutil.move(
                    str(games_base() / auto_id),
                    str(games_base() / game_id),
                )
            patch_state_game_id(game_id)
            server_state["matches"][game_id] = {"role": my_role, "seed": seed}
            return json.dumps({"accepted": True, "game_id": game_id})
        except Exception as exc:
            return json.dumps({"error": str(exc)})
