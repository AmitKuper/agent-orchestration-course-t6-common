"""ActorWrapper — the single interface the Agent calls every turn.

Wraps a BaseActor backend and delegates NL message generation to subclasses.
The Agent never calls a backend directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actor.base_actor import BaseActor

if TYPE_CHECKING:
    from game.state import ActionResult, ObservationState


class ActorWrapper:
    """Bridges the Agent and a swappable actor backend.

    Calls backend.get_action() for the move decision. Subclasses must
    implement _render_message to produce the mandatory NL message (PRD §3).
    """

    def __init__(self, backend: BaseActor, role: str) -> None:
        """Initialise with a backend and the agent's role.

        Args:
            backend: Any BaseActor implementation.
            role: "cop" or "thief".
        """
        self._backend = backend
        self._role = role

    def get_action(self, obs: ObservationState) -> tuple[str, str]:
        """Return (action, nl_message). Called by the Agent each turn.

        Args:
            obs: Current ObservationState from the game engine.

        Returns:
            A tuple of (action_string, natural_language_message).
        """
        action = self._backend.get_action(obs)
        message = self._render_message(obs, action)
        return action, message

    def on_result(self, obs: ObservationState, action: str, result: ActionResult) -> None:
        """Propagate action feedback to the backend.

        Args:
            obs: The observation that led to the action.
            action: The action that was submitted.
            result: The ActionResult returned by the game engine.
        """
        self._backend.on_result(obs, action, result)

    def _render_message(self, obs: ObservationState, action: str) -> str:
        """Generate the NL message for this action. Subclasses must override.

        Args:
            obs: Current observation.
            action: The chosen action string.

        Returns:
            A natural-language message describing the move intent.
        """
        raise NotImplementedError("Subclasses must implement _render_message")
