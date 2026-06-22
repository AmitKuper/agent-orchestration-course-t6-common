"""Gmail plugin guard — check whether the plugin is enabled before sending."""

from __future__ import annotations

import os


def is_enabled() -> bool:
    """Return True only when GMAIL_ENABLED=true AND GMAIL_RECIPIENT is set.

    The plugin is silently disabled if either variable is missing or falsy.
    This allows the internal game to run without any mail configuration.
    """
    enabled = os.environ.get("GMAIL_ENABLED", "false").strip().lower() == "true"
    recipient = os.environ.get("GMAIL_RECIPIENT", "").strip()
    return enabled and bool(recipient)


def get_recipient() -> str:
    """Return the GMAIL_RECIPIENT env var value.

    Returns:
        The recipient email address, or empty string if not set.
    """
    return os.environ.get("GMAIL_RECIPIENT", "").strip()
