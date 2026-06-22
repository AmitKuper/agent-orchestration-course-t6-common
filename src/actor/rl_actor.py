"""RLActorBackend — stub for the reinforcement-learning backend.

The full implementation (state encoder, policy, persistence) comes from a
separate repository and is not planned here. Dropping in the real implementation
requires only implementing get_action() and on_result().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actor.base_actor import BaseActor

if TYPE_CHECKING:
    from game.state import ActionResult, ObservationState


class RLActorBackend(BaseActor):
    """Placeholder for an RL-based actor.

    Both methods raise NotImplementedError. Replace with the real policy
    implementation when integrating the RL repository.
    """

    def get_action(self, obs: ObservationState) -> str:
        """Not implemented — requires RL policy from external repo.

        Args:
            obs: Current observation state.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("RLActorBackend: plug in RL policy from external repo.")

    def on_result(
        self,
        obs: ObservationState,
        action: str,
        result: ActionResult,
    ) -> None:
        """Not implemented — requires RL update rule from external repo.

        Args:
            obs: Observation that led to the action.
            action: The submitted action.
            result: The resulting ActionResult.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("RLActorBackend: plug in reward update from external repo.")
