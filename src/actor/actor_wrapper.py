"""ActorWrapper — the single interface the Agent calls every turn.

Wraps a BaseActor backend and generates the mandatory NL message alongside
the action. The Agent never calls a backend directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actor.base_actor import BaseActor
from game.constants import BARRIER_ACTION

if TYPE_CHECKING:
    from game.state import ActionResult, ObservationState

_MOVE_TEMPLATE = "Moving {action} to position {pos}."
_BARRIER_TEMPLATE = "Placing a barrier at {pos} to block the route."


class ActorWrapper:
    """Bridges the Agent and a swappable actor backend.

    Calls backend.get_action() for the move decision and generates a
    simple natural-language message template so every turn satisfies
    the mandatory free-text message protocol requirement (PRD §3).
    """

    def __init__(self, backend: BaseActor, role: str) -> None:
        """Initialise with a backend and the agent's role.

        Args:
            backend: Any BaseActor implementation.
            role: "cop" or "thief" — used in message templates.
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

    def on_result(
        self,
        obs: ObservationState,
        action: str,
        result: ActionResult,
    ) -> None:
        """Propagate action feedback to the backend.

        Args:
            obs: The observation that led to the action.
            action: The action that was submitted.
            result: The ActionResult returned by the game engine.
        """
        self._backend.on_result(obs, action, result)

    def _render_message(self, obs: ObservationState, action: str) -> str:
        """Generate a simple template message for the given action.

        Args:
            obs: Current observation (used to compute destination cell).
            action: The chosen action string.

        Returns:
            A short natural-language description of the move.
        """
        from game.constants import DIRECTIONS

        if action == BARRIER_ACTION:
            return _BARRIER_TEMPLATE.format(pos=list(obs.my_pos))
        delta = DIRECTIONS.get(action, (0, 0))
        dest = (obs.my_pos[0] + delta[0], obs.my_pos[1] + delta[1])
        return _MOVE_TEMPLATE.format(action=action, pos=list(dest))
