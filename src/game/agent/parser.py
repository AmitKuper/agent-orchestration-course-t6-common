"""Parser — extracts (action, message) from an LLM free-text response."""

from __future__ import annotations

import re

from game.constants import ALL_ACTIONS

# Matches "Action: NE" or "action: BARRIER" anywhere in the response
_ACTION_RE = re.compile(
    r"(?:^|\n)\s*[Aa]ction\s*:\s*([A-Z]+)\s*(?:\n|$)",
    re.MULTILINE,
)


class ParseError(ValueError):
    """Raised when no valid action can be extracted from the LLM response."""


def parse_response(text: str, legal_moves: list[str]) -> tuple[str, str]:
    """Extract (action, message) from a free-text LLM response.

    Strategy:
    1. Look for an explicit "Action: <TOKEN>" line.
    2. Validate the token against legal_moves (case-insensitive).
    3. Everything before the action line becomes the NL message.

    Args:
        text: Raw LLM response string.
        legal_moves: List of currently legal action strings (e.g. ["N","NE","BARRIER"]).

    Returns:
        Tuple of (action_string, nl_message).

    Raises:
        ParseError: If no valid action is found.
    """
    match = _ACTION_RE.search(text)
    if match:
        token = match.group(1).upper()
        if token in ALL_ACTIONS and token in [m.upper() for m in legal_moves]:
            action = token
            message = text[: match.start()].strip() or text.strip()
            return action, message
        raise ParseError(
            f"Parsed token '{token}' is not in legal moves: {legal_moves}"
        )

    # Fallback: scan for any legal move token as a standalone word
    upper_text = text.upper()
    for move in legal_moves:
        pattern = rf"\b{re.escape(move.upper())}\b"
        if re.search(pattern, upper_text):
            return move.upper(), text.strip()

    raise ParseError(
        f"No valid action found in response. Legal moves: {legal_moves}\n"
        f"Response was: {text[:200]!r}"
    )
