"""Renderer — converts ObservationState into human-readable prompt text for the LLM."""

from __future__ import annotations

from game.state import ObservationState

_ROLE_LABELS = {"cop": "COP", "thief": "THIEF"}


def render_observation(obs: ObservationState, last_opponent_message: str | None = None) -> str:
    """Render an ObservationState into a text prompt for the LLM.

    Args:
        obs: The actor's current observation from the game engine.
        last_opponent_message: The opponent's most recent free-text message, if any.

    Returns:
        A multi-line string suitable for injection into an LLM prompt.
    """
    role = _ROLE_LABELS.get(obs.actor, obs.actor.upper())
    lines = [
        f"Round {obs.round} | You are the {role} | Your position: {list(obs.my_pos)}",
    ]

    if obs.opponent_pos is not None:
        lines.append(f"Opponent position: {list(obs.opponent_pos)} [visible]")
    else:
        lines.append("Opponent position: unknown (outside view radius)")

    if obs.barriers:
        lines.append(f"Barriers on grid: {[list(b) for b in obs.barriers]}")
    else:
        lines.append("Barriers on grid: none")

    if obs.barriers_remaining is not None:
        lines.append(f"Barriers you may place: {obs.barriers_remaining}")

    lines.append(f"Legal moves: {', '.join(obs.legal_moves)}")

    if last_opponent_message:
        lines.append(f'Opponent\'s last message: "{last_opponent_message}"')

    lines.append(
        "\nRespond with a short natural-language message describing your intent, "
        "then on a new line write: Action: <MOVE>"
        "\nExample:\n  I'm moving to cut off your escape.\n  Action: NE"
    )
    return "\n".join(lines)
