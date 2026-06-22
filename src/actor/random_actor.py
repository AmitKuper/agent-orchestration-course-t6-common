"""RandomActorBackend — picks a random legal action each turn."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from actor.base_actor import BaseActor

if TYPE_CHECKING:
    from game.state import ObservationState


class RandomActorBackend(BaseActor):
    """Actor that selects uniformly at random from the legal moves.

    Used as the default/dummy backend for testing the pipeline without
    requiring an LLM or a trained policy.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Initialise with an optional RNG seed for reproducibility.

        Args:
            seed: Optional integer seed for the random number generator.
        """
        self._rng = random.Random(seed)

    def get_action(self, obs: ObservationState) -> str:
        """Return a uniformly random legal action.

        Args:
            obs: Current observation — legal_moves must be non-empty.

        Returns:
            A randomly chosen action string from obs.legal_moves.
        """
        return self._rng.choice(obs.legal_moves)
