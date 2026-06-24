"""MCP server entry point — assembles tools, prompts, resources, and REST routes.

Run with:
    python -m game.wrappers.mcp_server --port 8001 --games-dir games/server_a
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from fastmcp import FastMCP

from game.sdk.sdk import get_state as sdk_get_state
from game.sdk.sdk import new_game as sdk_new_game
from game.sdk.sdk import state_hash as sdk_hash
from game.sdk.sdk import submit_action as sdk_submit_action
from game.wrappers.mcp_agent_tools import register_agent_tools
from game.wrappers.mcp_prompts import register_prompts
from game.wrappers.mcp_resources import register_resources
from game.wrappers.mcp_routes import _patch_state_game_id, register_routes
from game.wrappers.mcp_state import games_base, server_state

mcp = FastMCP(
    name="cop-thief-game",
    instructions="Cop & Thief game engine. Use get_state then take_action to play.",
)
register_routes(mcp)
register_agent_tools(mcp)
register_prompts(mcp)
register_resources(mcp)


def _create_actor_wrapper(role: str) -> object:
    """Return an actor wrapper based on env-var priority.

    Priority:
      1. ACTOR_CLASS=<module>.<ClassName> — dynamically import and wrap that BaseActor subclass.
      2. ANTHROPIC_API_KEY or OLLAMA_BASE_URL — LLMActorWrapper.
      3. Fallback — RandomActorBackend.

    Args:
        role: "cop" or "thief".

    Returns:
        An ActorWrapper-compatible object with get_action(obs) -> (action, message).
    """
    actor_class_path = os.environ.get("ACTOR_CLASS")
    if actor_class_path:
        import importlib
        module_path, class_name = actor_class_path.rsplit(".", 1)
        actor_cls = getattr(importlib.import_module(module_path), class_name)
        table_path = os.environ.get("ACTOR_TABLE")
        if table_path and hasattr(actor_cls, "load"):
            actor = actor_cls.load(role=role, path=table_path)
        else:
            try:
                actor = actor_cls(role=role)
            except TypeError:
                actor = actor_cls()
        from actor.actor_wrapper import ActorWrapper
        return ActorWrapper(actor, role=role)
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OLLAMA_BASE_URL"):
        from actor.llm_actor import create_llm_wrapper
        return create_llm_wrapper(role)
    from actor.actor_wrapper import ActorWrapper
    from actor.random_actor import RandomActorBackend
    return ActorWrapper(RandomActorBackend(), role=role)


@mcp.tool()
def new_game_tool(
    game_id: str, cop_col: int, cop_row: int,
    thief_col: int, thief_row: int, seed: int,
) -> str:
    """Create a new game with pre-agreed positions (called after match setup)."""
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
        _patch_state_game_id(game_id)
        return json.dumps({"game_id": game_id})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def take_turn(game_id: str, actor: str) -> str:
    """Decide and submit one turn: get state, call actor, submit, forward, validate hash."""
    from game.wrappers.mcp_client import fetch_hash, send_receive_action

    try:
        obs = sdk_get_state(game_id, actor, games_base())
        wrapper = _create_actor_wrapper(actor)
        action, message = wrapper.get_action(obs)
        result = sdk_submit_action(game_id, actor, action,
                                   message=message, games_base=games_base())
        response = asdict(result)

        if result.success:
            try:
                send_receive_action(game_id, actor, action, message)
                local_h = sdk_hash(game_id, games_base())
                opp_h = fetch_hash(game_id)
                response["hash_match"] = (local_h == opp_h)
                response["local_hash"] = local_h
                response["opponent_hash"] = opp_h
            except Exception as comm_err:
                response["comm_error"] = str(comm_err)

        return json.dumps(response)
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
    mcp.run(transport="streamable-http", host=args.host, port=args.port, json_response=True)


if __name__ == "__main__":
    main()
