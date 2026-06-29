"""Opponent MCP call helper extracted from mcp_agent_tools.py."""

from __future__ import annotations

import asyncio
import json

_OPP_TIMEOUT = 30.0  # seconds; avoids hung TCP connections to unresponsive opponents
_RECV_RETRIES = 3    # retry attempts before declaring comm_error


async def call_opponent(
    opp_url: str, api_key: str, game_id: str,
    actor: str, action: str, message: str,
) -> tuple[str | None, str | None]:
    """Forward action to opponent with per-call timeout and retry.

    Args:
        opp_url: Opponent MCP base URL (no trailing slash, no /mcp suffix).
        api_key: Bearer token for outbound requests.
        game_id: The active game identifier.
        actor: "cop" or "thief".
        action: Move direction or BARRIER.
        message: Natural-language intent message.

    Returns:
        (opp_hash, None) on success, (None, error_string) after all retries fail.
    """
    from fastmcp import Client
    from fastmcp.client.auth.bearer import BearerAuth

    auth = BearerAuth(api_key)
    last_err: str | None = None
    for attempt in range(_RECV_RETRIES):
        try:
            async with Client(opp_url + "/mcp", auth=auth, timeout=_OPP_TIMEOUT) as opp:
                recv = await opp.call_tool("receive_action", {
                    "game_id": game_id, "actor": actor,
                    "action": action, "message": message,
                })
                recv_data = json.loads(recv.content[0].text if recv.content else "{}")
                if "success" not in recv_data:
                    last_err = f"receive_action: {recv_data.get('error')}"
                    if attempt < _RECV_RETRIES - 1:
                        await asyncio.sleep(2.0)
                    continue
                hr = await opp.call_tool("get_hash", {"game_id": game_id})
                opp_h = json.loads(hr.content[0].text if hr.content else "{}").get("hash", "")
            return opp_h, None
        except Exception as exc:
            last_err = str(exc)
            if attempt < _RECV_RETRIES - 1:
                await asyncio.sleep(2.0)
    return None, last_err
