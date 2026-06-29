"""Actor-mode game loop: drives alternating turns via Q-table + NL messaging."""

from __future__ import annotations

import json
import os

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

from match_helpers import API_KEY
from match_helpers.actor_turn import (
    _SYSTEM_COP,
    _SYSTEM_THIEF,
    _actor_turn,
    _tech_loss,
)
from match_helpers.log_reader import _board_str


async def _actor_game_loop(
    url_a: str, url_b: str, game_id: str, max_rounds: int,
    turn_timeout: float = 30.0, max_forfeits: int = 3,
    time_debug: bool = False,
) -> dict:
    """Drive turns via Q-table → NL message → take_action per PRD §6.

    Args:
        url_a: URL of the thief server.
        url_b: URL of the cop server.
        game_id: Active game identifier.
        max_rounds: Maximum rounds before thief wins.
        turn_timeout: Per-tool-call timeout in seconds.
        max_forfeits: Consecutive forfeits before technical loss.
        time_debug: If True, print per-phase timing for every turn.

    Returns:
        Final ActionResult dict, or a technical-loss sentinel on divergence.
    """
    from game.shared.gatekeeper import Gatekeeper

    gk = Gatekeeper(model=os.environ.get("LLM_MODEL") or None)
    auth = BearerAuth(API_KEY)
    last_result: dict = {}
    consec_forfeits: dict[str, int] = {"thief": 0, "cop": 0}
    last_messages: dict[str, str] = {"thief": "", "cop": ""}

    async with Client(url_a + "/mcp", auth=auth, timeout=turn_timeout) as ca, \
               Client(url_b + "/mcp", auth=auth, timeout=turn_timeout) as cb:
        game_over, round_num = False, 0
        while not game_over and round_num < max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for client, actor, system in [
                (ca, "thief", _SYSTEM_THIEF),
                (cb, "cop", _SYSTEM_COP),
            ]:
                other = cb if client is ca else ca
                opponent = "cop" if actor == "thief" else "thief"
                result = await _actor_turn(
                    client, actor, game_id, gk, system, turn_timeout,
                    opponent_msg=last_messages[opponent],
                    time_debug=time_debug,
                )
                if result.get("forfeit"):
                    consec_forfeits[actor] += 1
                    if consec_forfeits[actor] >= max_forfeits:
                        return _tech_loss(f"consecutive_forfeits:{actor}")
                    streak = consec_forfeits[actor]
                    print(f"  {actor}: forfeit ({result.get('reason')}) — streak {streak}")
                    continue
                consec_forfeits[actor] = 0
                sent_msg = result.pop("_msg", "")
                action = result.pop("_action", None)
                if sent_msg:
                    last_messages[actor] = sent_msg
                    print(f"  {actor} says: \"{sent_msg}\"")
                # Orchestrator applies the action on the peer server when comm_error
                # prevents the acting server from notifying the opponent itself.
                # Must also run on the game-ending move to avoid false tech loss.
                if "comm_error" in result and action:
                    try:
                        await other.call_tool("receive_action", {
                            "game_id": game_id, "actor": actor,
                            "action": action, "message": sent_msg,
                        })
                        ha = await client.call_tool("get_hash", {"game_id": game_id})
                        hb = await other.call_tool("get_hash", {"game_id": game_id})
                        h1 = json.loads(ha.content[0].text if ha.content else "{}").get("hash")
                        h2 = json.loads(hb.content[0].text if hb.content else "{}").get("hash")
                        if h1 and h1 == h2:
                            result.pop("comm_error")
                            result["hash_match"] = True
                            print(f"  [sync] orchestrator recovered sync for {actor}")
                    except Exception as sync_err:
                        result["comm_error"] = str(sync_err)
                if result.get("hash_match") is False:
                    return _tech_loss("hash_mismatch")
                if "comm_error" in result:
                    return _tech_loss(f"comm_error:{result['comm_error']}")
                last_result = result
                if result.get("game_over"):
                    game_over = True
                    break
            board = _board_str(game_id)
            if board:
                print(board)
    return last_result
