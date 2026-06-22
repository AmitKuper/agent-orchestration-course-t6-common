"""BaseActor — abstract interface every actor backend must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import ActionResult, ObservationState


class BaseActor(ABC):
    """Abstract base for all actor backends.

    The ActorWrapper calls get_action() to obtain a move and on_result()
    to deliver feedback after the action resolves. Learning backends use
    on_result() for reward updates; stateless backends ignore it.
    """

    @abstractmethod
    def get_action(self, obs: ObservationState) -> str:
        """Return one legal action string given the current observation.

        Args:
            obs: The actor's current ObservationState (legal_moves included).

        Returns:
            A legal action string, e.g. "NE" or "BARRIER".
        """

    def on_result(
        self,
        obs: ObservationState,
        action: str,
        result: ActionResult,
    ) -> None:
        """Called after the action resolves. Default is a no-op.

        Args:
            obs: The observation that led to the action.
            action: The action that was submitted.
            result: The ActionResult returned by the game engine.
        """
