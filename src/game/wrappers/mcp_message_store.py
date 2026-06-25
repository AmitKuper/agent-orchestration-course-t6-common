"""In-memory store for the last NL message each actor sent, per game.

Both receive_action (sync tools) and take_action (agent tools) write here.
get_state reads the opponent's last message and injects it into ObservationState
so LLM-mode agents can reason from their opponent's natural-language intent.
"""

from __future__ import annotations

# game_id -> {"cop": last_message, "thief": last_message}
_messages: dict[str, dict[str, str]] = {}


def record_message(game_id: str, actor: str, message: str) -> None:
    """Store the most recent NL message sent by actor for game_id.

    Args:
        game_id: The active game identifier.
        actor: "cop" or "thief".
        message: The natural-language message the actor sent with its action.
    """
    if not message:
        return
    if game_id not in _messages:
        _messages[game_id] = {}
    _messages[game_id][actor] = message


def get_opponent_message(game_id: str, actor: str) -> str | None:
    """Return the opponent's last NL message, or None if not yet sent.

    Args:
        game_id: The active game identifier.
        actor: The *requesting* actor ("cop" or "thief") — returns the OTHER actor's message.

    Returns:
        The opponent's last message string, or None.
    """
    opponent = "thief" if actor == "cop" else "cop"
    return _messages.get(game_id, {}).get(opponent)


def clear_game(game_id: str) -> None:
    """Remove all stored messages for a completed or voided game.

    Args:
        game_id: The game identifier to purge.
    """
    _messages.pop(game_id, None)
