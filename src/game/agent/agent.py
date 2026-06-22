"""Agent — retry loop that bridges ActorWrapper decisions with the game SDK."""

from __future__ import annotations

from pathlib import Path

from game.agent.renderer import render_observation
from game.constants import COP, THIEF
from game.sdk.sdk import get_state, submit_action
from game.state import ActionResult

_FORFEIT_ACTION = "S"  # default direction used when forfeiting (no movement intended)


class TechnicalLossError(RuntimeError):
    """Raised when max_consecutive_forfeits is exceeded."""


class Agent:
    """Drives one side of a game turn-by-turn using an ActorWrapper.

    The Agent asks the wrapper what to do, submits the action through
    the SDK, handles illegal-action retries, and tracks forfeits.
    """

    def __init__(
        self,
        actor_wrapper: object,
        actor: str,
        max_illegal_retries: int = 2,
        max_consecutive_forfeits: int = 3,
        games_base: Path | None = None,
    ) -> None:
        """Initialise the Agent for one player role.

        Args:
            actor_wrapper: ActorWrapper instance with get_action() and on_result().
            actor: "cop" or "thief".
            max_illegal_retries: Re-prompt attempts before forfeiting a turn.
            max_consecutive_forfeits: Forfeits in a row before TechnicalLossError.
            games_base: Optional override for the games root directory.
        """
        if actor not in (COP, THIEF):
            raise ValueError(f"actor must be 'cop' or 'thief', got {actor!r}")
        self._wrapper = actor_wrapper
        self._actor = actor
        self._max_retries = max_illegal_retries
        self._max_forfeits = max_consecutive_forfeits
        self._games_base = games_base
        self._consecutive_forfeits = 0
        self._last_opponent_message: str | None = None

    def take_turn(self, game_id: str) -> ActionResult:
        """Take one turn: decide action, submit, handle retries and forfeits.

        Args:
            game_id: The active game identifier.

        Returns:
            The ActionResult from the successful (or forfeited) submission.

        Raises:
            TechnicalLossError: If max_consecutive_forfeits is exceeded.
        """
        obs = get_state(game_id, self._actor, self._games_base)
        action, message = self._wrapper.get_action(obs)

        for attempt in range(self._max_retries + 1):
            result = submit_action(game_id, self._actor, action,
                                   message=message, games_base=self._games_base)
            if result.success:
                self._wrapper.on_result(obs, action, result)
                self._consecutive_forfeits = 0
                return result
            # Re-render with the error hint and retry
            if attempt < self._max_retries:
                hint = render_observation(obs, self._last_opponent_message)
                hint += f"\n\nPrevious action '{action}' was illegal: {result.error}\nTry again."
                action, message = self._wrapper.get_action(obs)

        # Exhausted retries — forfeit the turn
        self._consecutive_forfeits += 1
        if self._consecutive_forfeits >= self._max_forfeits:
            raise TechnicalLossError(
                f"{self._actor} forfeited {self._consecutive_forfeits} turns in a row"
            )
        # Submit a no-op (stay in place by retrying current pos direction — engine will reject
        # and we mark forfeit; we return the last failed result as the forfeit result)
        return result  # type: ignore[return-value]

    def set_opponent_message(self, message: str | None) -> None:
        """Store the opponent's most recent NL message for the next render.

        Args:
            message: The opponent's free-text message from their last turn.
        """
        self._last_opponent_message = message
