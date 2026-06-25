"""LLMMessageWrapper — any BaseActor for action decisions; LLM generates the NL message.

Use this when the strategy (action) comes from a trained or rule-based backend
but the protocol requires a free-text NL message (PRD §3).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from actor.actor_wrapper import ActorWrapper
from actor.llm_actor import _SYSTEM_COP, _SYSTEM_THIEF

if TYPE_CHECKING:
    from actor.base_actor import BaseActor
    from game.shared.gatekeeper import Gatekeeper
    from game.state import ObservationState

_DIRECTION_NAMES: dict[str, str] = {
    "N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
    "S": "south", "SW": "southwest", "W": "west", "NW": "northwest",
    "BARRIER": "barrier",
}

_MESSAGE_PROMPT = (
    "You chose action {action}. "
    "Complete this sentence with 1-3 words and nothing else: "
    "'Moving {direction}___.' "
    "Your reply must start with 'Moving {direction}'."
)


class LLMMessageWrapper(ActorWrapper):
    """Combines any action-deciding backend with LLM-generated NL messages."""

    def __init__(self, backend: BaseActor, gatekeeper: Gatekeeper, role: str) -> None:
        """Initialise with an action backend, LLM gatekeeper, and player role.

        Args:
            backend: Any BaseActor implementation for action decisions.
            gatekeeper: Rate-limited LLM call wrapper for message generation.
            role: "cop" or "thief".
        """
        super().__init__(backend, role)
        self._gk = gatekeeper
        self._system = _SYSTEM_COP if role == "cop" else _SYSTEM_THIEF

    def _render_message(self, obs: ObservationState, action: str) -> str:
        """Ask the LLM to generate a one-sentence message for the chosen action.

        Args:
            obs: Current observation (unused; role context comes from system prompt).
            action: The action chosen by the backend.

        Returns:
            LLM-generated NL message string.
        """
        direction = _DIRECTION_NAMES.get(action, action.lower())
        prompt = _MESSAGE_PROMPT.format(action=action, direction=direction)
        return self._gk.call(
            [{"role": "user", "content": prompt}], system=self._system
        ).strip()


def create_llm_message_wrapper(backend: BaseActor, role: str) -> LLMMessageWrapper:
    """Wrap any BaseActor backend with LLM message generation.

    Reads ANTHROPIC_API_KEY or OLLAMA_BASE_URL to configure the Gatekeeper.
    Optionally reads LLM_MODEL to override the default model.

    Args:
        backend: Trained or custom actor for action decisions.
        role: "cop" or "thief".

    Returns:
        LLMMessageWrapper ready to play.
    """
    from game.shared.gatekeeper import Gatekeeper

    model = os.environ.get("LLM_MODEL") or None
    gk = Gatekeeper(model=model)
    return LLMMessageWrapper(backend, gk, role)
