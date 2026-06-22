"""HTTP client for server-to-server calls to the opponent MCP server."""

from __future__ import annotations

import os
from typing import Any

import httpx

from game.wrappers.mcp_auth import outbound_headers

_TIMEOUT = 30.0


def _opponent_url() -> str:
    """Return the base URL of the opponent server from the environment."""
    url = os.environ.get("OPPONENT_MCP_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("OPPONENT_MCP_URL is not set in the environment.")
    return url


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the opponent server's custom REST endpoint.

    Args:
        path: URL path, e.g. "/game/receive_action".
        payload: JSON-serialisable request body.

    Returns:
        Parsed JSON response dict.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        RuntimeError: If OPPONENT_MCP_URL is not configured.
    """
    url = _opponent_url() + path
    response = httpx.post(
        url,
        json=payload,
        headers=outbound_headers(),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def send_receive_action(
    game_id: str,
    actor: str,
    action: str,
    message: str | None,
) -> dict[str, Any]:
    """Push a completed action to the opponent's engine.

    Args:
        game_id: The active game identifier.
        actor: "cop" or "thief" (the acting side).
        action: The action string that was applied locally.
        message: The NL message sent alongside the action.

    Returns:
        Dict with keys "success", "game_over", "winner", "win_reason", "hash".
    """
    return _post("/game/receive_action", {
        "game_id": game_id,
        "actor": actor,
        "action": action,
        "message": message,
    })


def fetch_hash(game_id: str) -> str:
    """Retrieve the opponent's canonical state hash.

    Args:
        game_id: The active game identifier.

    Returns:
        8-character hex hash string from the opponent's engine.
    """
    result = _post("/game/hash", {"game_id": game_id})
    return result["hash"]


def propose_match(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a match proposal to the opponent server.

    Args:
        payload: Dict with seed, mechanics, grid_size, game_id, roles.

    Returns:
        Opponent's response dict (accepted, game_id, etc.).
    """
    return _post("/game/propose_match", payload)
