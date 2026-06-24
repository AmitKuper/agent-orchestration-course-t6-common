"""LLM-backed actor — drives game decisions via Gatekeeper + renderer + parser.

LLMActorBackend calls the LLM with the rendered ObservationState and parses
the response. On parse failure it re-prompts the LLM with a clarification
request (up to max_retries times) before raising ParseError.
LLMActorWrapper extends ActorWrapper to surface the LLM's NL message.
create_llm_wrapper is the public factory.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from actor.actor_wrapper import ActorWrapper
from actor.base_actor import BaseActor

if TYPE_CHECKING:
    from game.shared.gatekeeper import Gatekeeper
    from game.state import ObservationState

_SYSTEM_COP = (
    "You are the COP in a Cop & Thief pursuit game on a 5×5 grid. "
    "Goal: capture the thief by landing on the same cell. "
    "You may move in 8 directions (N/NE/E/SE/S/SW/W/NW) or place a BARRIER on your "
    "current cell (max 5 per game). "
    "Reply with a short message describing your intent, then on a new line: Action: <MOVE>"
)
_SYSTEM_THIEF = (
    "You are the THIEF in a Cop & Thief pursuit game on a 5×5 grid. "
    "Goal: survive 25 rounds without being captured. "
    "Move in 8 directions (N/NE/E/SE/S/SW/W/NW); you cannot place barriers. "
    "Reply with a short message describing your intent, then on a new line: Action: <MOVE>"
)
_MAX_FORMAT_RETRIES = 2
_CLARIFY_TEMPLATE = (
    "I could not parse your move. {error}\n"
    "Legal moves are: {moves}.\n"
    "Please reply again: one or two sentences describing your intent, "
    "then on a new line exactly: Action: <MOVE>"
)


class LLMActorBackend(BaseActor):
    """Actor backend that queries an LLM for each move decision.

    Renders the ObservationState into a text prompt, calls the Gatekeeper,
    and parses the response. On ParseError it appends a clarification request
    to the conversation and retries up to max_retries times before raising.
    The extracted NL message is stored in last_message for LLMActorWrapper.
    """

    def __init__(
        self,
        gatekeeper: Gatekeeper,
        system_prompt: str | None = None,
        max_retries: int = _MAX_FORMAT_RETRIES,
    ) -> None:
        """Initialise with a Gatekeeper and optional system prompt.

        Args:
            gatekeeper: Rate-limited LLM call wrapper.
            system_prompt: Role-specific system prompt; defaults to generic if None.
            max_retries: How many clarification re-prompts to attempt on ParseError.
        """
        self._gk = gatekeeper
        self._system = system_prompt
        self._max_retries = max_retries
        self.last_message: str = ""

    def get_action(self, obs: ObservationState) -> str:
        """Query the LLM and return a legal action string.

        Builds a multi-turn conversation: initial prompt, then clarification
        requests on each ParseError. Raises ParseError if all attempts fail.

        Args:
            obs: Current ObservationState from the game engine.

        Returns:
            A legal action string from obs.legal_moves.

        Raises:
            ParseError: If the LLM fails to produce a valid action after all retries.
        """
        from game.agent.parser import ParseError, parse_response
        from game.agent.renderer import render_observation

        messages: list[dict[str, str]] = [
            {"role": "user", "content": render_observation(obs)},
        ]
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            response = self._gk.call(messages, system=self._system)
            try:
                action, message = parse_response(response, obs.legal_moves)
                self.last_message = message
                return action
            except ParseError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    clarification = _CLARIFY_TEMPLATE.format(
                        error=exc, moves=", ".join(obs.legal_moves)
                    )
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": clarification})

        raise ParseError(
            f"No valid action after {self._max_retries + 1} attempt(s): {last_error}"
        )


class LLMActorWrapper(ActorWrapper):
    """ActorWrapper subclass that returns the LLM-generated NL message.

    Overrides _render_message so the (action, message) tuple returned by
    get_action carries the LLM's intent text rather than a canned template.
    """

    def __init__(self, gatekeeper: Gatekeeper, role: str) -> None:
        """Initialise with a Gatekeeper and player role.

        Args:
            gatekeeper: Rate-limited LLM call wrapper.
            role: "cop" or "thief" — selects the system prompt.
        """
        system = _SYSTEM_COP if role == "cop" else _SYSTEM_THIEF
        backend = LLMActorBackend(gatekeeper, system_prompt=system)
        super().__init__(backend, role)

    def _render_message(self, obs: ObservationState, action: str) -> str:
        """Return the LLM's NL message in place of the default template.

        Args:
            obs: Current observation (unused; message comes from LLM).
            action: Chosen action (unused; message comes from LLM).

        Returns:
            The NL message captured from the LLM response.
        """
        backend = cast(LLMActorBackend, self._backend)
        return backend.last_message


def create_llm_wrapper(role: str) -> LLMActorWrapper:
    """Factory: build an LLMActorWrapper from environment configuration.

    Reads ANTHROPIC_API_KEY (Anthropic) or OLLAMA_BASE_URL (Ollama) to select
    the backend. Optionally reads LLM_MODEL to override the default model.

    Args:
        role: "cop" or "thief".

    Returns:
        A configured LLMActorWrapper ready to play.
    """
    from game.shared.gatekeeper import Gatekeeper

    model = os.environ.get("LLM_MODEL") or None
    gk = Gatekeeper(model=model)
    return LLMActorWrapper(gk, role)
