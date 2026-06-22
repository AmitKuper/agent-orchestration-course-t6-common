"""MCP auth helpers — validate inbound API keys and build outbound headers."""

from __future__ import annotations

import os


def get_allowed_keys() -> set[str]:
    """Return the set of accepted inbound API keys from the environment.

    Reads MCP_ALLOWED_API_KEYS (comma-separated). Returns an empty set
    if the variable is unset, which causes all requests to be rejected.
    """
    raw = os.environ.get("MCP_ALLOWED_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def get_outbound_key() -> str:
    """Return the API key this server presents on outbound requests."""
    return os.environ.get("MCP_API_KEY", "")


def validate_key(key: str | None) -> bool:
    """Return True if key is in the allowed set.

    An empty allowed set (env var not configured) rejects all requests,
    so deployments without auth configured fail closed.

    Args:
        key: The API key from the inbound request header, or None.
    """
    if not key:
        return False
    allowed = get_allowed_keys()
    if not allowed:
        return False
    return key in allowed


def outbound_headers() -> dict[str, str]:
    """Return headers dict to include on all outbound HTTP requests.

    Returns:
        Dict with X-API-Key header if MCP_API_KEY is set, else empty dict.
    """
    key = get_outbound_key()
    if key:
        return {"X-API-Key": key}
    return {}
