"""Actor-mode turn execution: Q-table action → NL message → take_action."""

from __future__ import annotations

import asyncio
import json
import time

_SYSTEM_COP = (
    "You are the COP in a 5×5 Cop & Thief grid game. "
    "Capture the thief by landing on its cell. "
    "You may move N NE E SE S SW W NW or place BARRIER on your cell (max 5). "
    "Call get_state to observe the board, then take_action with your move "
    "and a one-sentence message."
)
_SYSTEM_THIEF = (
    "You are the THIEF in a 5×5 Cop & Thief grid game. "
    "Survive 25 rounds without being captured. "
    "You may move N NE E SE S SW W NW. No barriers. "
    "Call get_state to observe the board, then take_action with your move "
    "and a one-sentence message."
)
_DIRS: dict[str, str] = {
    "N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
    "S": "south", "SW": "southwest", "W": "west", "NW": "northwest",
    "BARRIER": "barrier on current cell",
}


def _tech_loss(reason: str) -> dict:
    """Return a technical-loss sentinel dict."""
    return {"technical_loss": True, "reason": reason}


async def _actor_turn(
    client: object, actor: str, game_id: str,
    gk: object, system: str, timeout: float,
    opponent_msg: str = "", time_debug: bool = False,
) -> dict:
    """Execute one actor turn: get_actor_action → contextual NL message → take_action.

    Args:
        client: FastMCP Client connected to the actor's server.
        actor: "cop" or "thief".
        game_id: Active game identifier.
        gk: Gatekeeper instance for LLM calls.
        system: System prompt for NL message generation.
        timeout: Per-tool-call timeout in seconds.
        opponent_msg: The opponent's last NL message, for contextual response.
        time_debug: If True, print per-phase timing to stdout.

    Returns:
        ActionResult dict with "_msg" and "_action" keys, or {"forfeit": True} on error.
    """
    def _ms(t: float) -> str:
        return f"{int((time.perf_counter() - t) * 1000)}ms"

    try:
        t0 = time.perf_counter()
        ar = await asyncio.wait_for(
            client.call_tool("get_actor_action", {"game_id": game_id, "actor": actor}),
            timeout=timeout,
        )
        if time_debug:
            print(f"  [perf] {actor} qtable={_ms(t0)}")
        adata = json.loads(ar.content[0].text if ar.content else "{}")
        if "error" in adata:
            return {"forfeit": True, "reason": adata["error"]}
        action = adata["action"]
        direction = _DIRS.get(action, action.lower())
        if opponent_msg:
            prompt = (
                f"You are the {actor.upper()} in a cop-thief pursuit game. "
                f"Opponent's last message: '{opponent_msg}'. "
                f"You chose to move {direction}. "
                "In one sentence describe your move."
            )
        else:
            prompt = (
                f"You are the {actor.upper()} in a cop-thief pursuit game "
                f"and you are moving {direction}. "
                "In one sentence describe your intent."
            )
        t1 = time.perf_counter()
        msg = await asyncio.to_thread(gk.call, [{"role": "user", "content": prompt}], system)
        if time_debug:
            print(f"  [perf] {actor} llm={_ms(t1)}")
        t2 = time.perf_counter()
        tr = await asyncio.wait_for(
            client.call_tool(
                "take_action",
                {"game_id": game_id, "actor": actor, "action": action, "message": msg.strip()},
            ),
            timeout=timeout,
        )
        if time_debug:
            print(f"  [perf] {actor} take_action={_ms(t2)}  turn_total={_ms(t0)}")
        result = json.loads(tr.content[0].text if tr.content else "{}")
        if not result.get("success", True):
            return {"forfeit": True, "reason": "illegal_action"}
        result["_msg"] = msg.strip()
        result["_action"] = action
        return result
    except TimeoutError:
        return {"forfeit": True, "reason": "timeout"}
