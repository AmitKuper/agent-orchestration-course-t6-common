"""Core Game state machine for the Cop & Thief pursuit game.

External callers use only: Game.new(), submit_action(), get_state(), state_hash().
Internal logic lives in GameRules (game_rules.py).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from game.actions import BarrierAction, parse_action
from game.constants import ACTORS, COP
from game.game_rules import GameRules
from game.game_state import GameState
from game.state import ActionResult, ObservationState


class Game(GameRules):
    """Pure-Python state machine for a single Cop & Thief sub-game."""

    def __init__(self, state: GameState) -> None:
        """Initialise with an existing GameState (use Game.new() instead)."""
        self._state = state

    @classmethod
    def new(
        cls,
        game_id: str,
        grid_size: tuple[int, int],
        cop_pos: tuple[int, int],
        thief_pos: tuple[int, int],
        mechanics: dict[str, Any] | None = None,
    ) -> Game:
        """Create and return a new Game instance.

        Args:
            game_id: Unique identifier for this game.
            grid_size: (cols, rows) of the grid.
            cop_pos: Starting (col, row) of the cop, 0-indexed.
            thief_pos: Starting (col, row) of the thief, 0-indexed.
            mechanics: Optional dict overriding default settings.

        Raises:
            ValueError: If positions are off-grid or identical.
        """
        from game.constants import DEFAULT_MAX_BARRIERS, DEFAULT_MAX_MOVES

        cols, rows = grid_size
        mechanics = mechanics or {}
        cls._validate_position(cop_pos, cols, rows, "cop_pos")
        cls._validate_position(thief_pos, cols, rows, "thief_pos")
        if cop_pos == thief_pos:
            raise ValueError("cop_pos and thief_pos must not be identical")

        return cls(GameState(
            game_id=game_id, grid_cols=cols, grid_rows=rows,
            cop_pos=cop_pos, thief_pos=thief_pos, barriers=[],
            round=0, turn=0, barriers_placed=0,
            max_moves=int(mechanics.get("max_moves", DEFAULT_MAX_MOVES)),
            max_barriers=int(mechanics.get("max_barriers", DEFAULT_MAX_BARRIERS)),
            game_over=False, winner=None, win_reason=None, mechanics=mechanics,
        ))

    def submit_action(self, actor: str, action: str) -> ActionResult:
        """Apply an action and advance state.

        Args:
            actor: "cop" or "thief".
            action: Direction string or "BARRIER".

        Returns:
            ActionResult with success/failure and any game-over outcome.
        """
        s = self._state
        if actor not in ACTORS:
            return ActionResult(
                success=False, error=f"Unknown actor: {actor!r}",
                game_over=False, winner=None, win_reason=None,
            )
        if s.game_over:
            return ActionResult(
                success=False, error="Game is already over.",
                game_over=True, winner=s.winner, win_reason=s.win_reason,
            )
        try:
            parsed = parse_action(action)
        except ValueError as exc:
            return ActionResult(
                success=False, error=str(exc),
                game_over=False, winner=None, win_reason=None,
            )
        if isinstance(parsed, BarrierAction):
            return self._apply_barrier(actor)
        return self._apply_move(actor, parsed)

    def get_state(self, actor: str) -> ObservationState:
        """Return actor-scoped observation state with partial observation enforced.

        The opponent position is hidden (set to None) when the Chebyshev
        distance exceeds view_radius from mechanics (default DEFAULT_VIEW_RADIUS).

        Args:
            actor: "cop" or "thief".

        Raises:
            ValueError: If actor is not "cop" or "thief".
        """
        from game.constants import DEFAULT_VIEW_RADIUS

        if actor not in ACTORS:
            raise ValueError(f"Unknown actor: {actor!r}")
        s = self._state
        if actor == COP:
            my_pos, opp_pos = s.cop_pos, s.thief_pos
            barriers_remaining: int | None = s.max_barriers - s.barriers_placed
        else:
            my_pos, opp_pos = s.thief_pos, s.cop_pos
            barriers_remaining = None
        view_radius = int(s.mechanics.get("view_radius", DEFAULT_VIEW_RADIUS))
        chebyshev = max(abs(my_pos[0] - opp_pos[0]), abs(my_pos[1] - opp_pos[1]))
        visible_opp = opp_pos if chebyshev <= view_radius else None
        return ObservationState(
            actor=actor, round=s.round, my_pos=my_pos, opponent_pos=visible_opp,
            barriers=list(s.barriers), legal_moves=self._compute_legal_moves(actor),
            barriers_remaining=barriers_remaining,
        )

    def state_hash(self) -> str:
        """Return an 8-char deterministic hex digest of the current state."""
        canonical = json.dumps(self._state.to_dict(), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:8]

    def to_dict(self) -> dict:
        """Return full state as a JSON-serializable dict."""
        return self._state.to_dict()

    @classmethod
    def from_dict(cls, d: dict) -> Game:
        """Restore a Game from a dict loaded from state.json."""
        return cls(GameState.from_dict(d))
