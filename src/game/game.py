"""Core Game state machine for the Cop & Thief pursuit game."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from game.actions import BarrierAction, MoveAction, parse_action
from game.constants import (
    ACTORS,
    ALL_MOVE_ACTIONS,
    BARRIER_ACTION,
    COP,
    DEFAULT_MAX_BARRIERS,
    DEFAULT_MAX_MOVES,
    DIRECTIONS,
    THIEF,
    WIN_CAPTURE,
    WIN_COP_TRAPPED,
    WIN_THIEF_SURVIVED,
    WIN_THIEF_TRAPPED,
)
from game.state import ActionResult, ObservationState


@dataclass
class GameState:
    """Full internal game state (serialized to state.json)."""

    game_id: str
    grid_cols: int
    grid_rows: int
    cop_pos: tuple[int, int]
    thief_pos: tuple[int, int]
    barriers: list[tuple[int, int]]
    round: int
    barriers_placed: int
    max_moves: int
    max_barriers: int
    game_over: bool
    winner: str | None
    win_reason: str | None
    mechanics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GameState:
        """Restore from dict (e.g. loaded from state.json)."""
        d = dict(d)
        d["cop_pos"] = tuple(d["cop_pos"])
        d["thief_pos"] = tuple(d["thief_pos"])
        d["barriers"] = [tuple(b) for b in d["barriers"]]
        return cls(**d)


class Game:
    """Pure-Python state machine for a single Cop & Thief sub-game.

    All external callers (CLI, CrewAI, MCP) interact exclusively through:
        - Game.new()         — construct a new game
        - game.submit_action()  — advance state by one action
        - game.get_state()      — read actor-scoped observation
        - game.state_hash()     — canonical hash of current state
    """

    def __init__(self, state: GameState) -> None:
        """Initialise with an existing GameState (use Game.new() instead)."""
        self._state = state

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def new(
        cls,
        game_id: str,
        grid_size: tuple[int, int],
        cop_pos: tuple[int, int],
        thief_pos: tuple[int, int],
        mechanics: dict[str, Any] | None = None,
    ) -> Game:
        """Create a new game instance.

        Args:
            game_id: Unique identifier for this game.
            grid_size: (cols, rows) of the grid (both 1-indexed max).
            cop_pos: Starting (col, row) of the cop, 0-indexed.
            thief_pos: Starting (col, row) of the thief, 0-indexed.
            mechanics: Optional dict of game settings; uses defaults if None.

        Returns:
            A new Game instance.

        Raises:
            ValueError: If positions are off-grid, identical, or invalid.
        """
        cols, rows = grid_size
        mechanics = mechanics or {}
        max_moves = int(mechanics.get("max_moves", DEFAULT_MAX_MOVES))
        max_barriers = int(mechanics.get("max_barriers", DEFAULT_MAX_BARRIERS))

        cls._validate_position(cop_pos, cols, rows, "cop_pos")
        cls._validate_position(thief_pos, cols, rows, "thief_pos")
        if cop_pos == thief_pos:
            raise ValueError("cop_pos and thief_pos must not be identical")

        state = GameState(
            game_id=game_id,
            grid_cols=cols,
            grid_rows=rows,
            cop_pos=cop_pos,
            thief_pos=thief_pos,
            barriers=[],
            round=0,
            barriers_placed=0,
            max_moves=max_moves,
            max_barriers=max_barriers,
            game_over=False,
            winner=None,
            win_reason=None,
            mechanics=mechanics,
        )
        return cls(state)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_action(self, actor: str, action: str) -> ActionResult:
        """Apply an action for the given actor and advance the game state.

        Args:
            actor: "cop" or "thief".
            action: Action string — direction or "BARRIER".

        Returns:
            ActionResult indicating success/failure and game-over state.
        """
        s = self._state

        if actor not in ACTORS:
            return ActionResult(
                success=False, error=f"Unknown actor: {actor!r}", game_over=False,
                winner=None, win_reason=None,
            )
        if s.game_over:
            return ActionResult(
                success=False, error="Game is already over.", game_over=True,
                winner=s.winner, win_reason=s.win_reason,
            )

        try:
            parsed = parse_action(action)
        except ValueError as exc:
            return ActionResult(
                success=False, error=str(exc), game_over=False, winner=None, win_reason=None,
            )

        if isinstance(parsed, BarrierAction):
            return self._apply_barrier(actor)
        return self._apply_move(actor, parsed)

    def get_state(self, actor: str) -> ObservationState:
        """Return actor-scoped observation state.

        Args:
            actor: "cop" or "thief".

        Returns:
            ObservationState for the given actor.

        Raises:
            ValueError: If actor is not "cop" or "thief".
        """
        if actor not in ACTORS:
            raise ValueError(f"Unknown actor: {actor!r}")

        s = self._state
        if actor == COP:
            my_pos = s.cop_pos
            opp_pos = s.thief_pos
            barriers_remaining: int | None = s.max_barriers - s.barriers_placed
        else:
            my_pos = s.thief_pos
            opp_pos = s.cop_pos
            barriers_remaining = None

        legal = self._compute_legal_moves(actor)

        return ObservationState(
            actor=actor,
            round=s.round,
            my_pos=my_pos,
            opponent_pos=opp_pos,
            barriers=list(s.barriers),
            legal_moves=legal,
            barriers_remaining=barriers_remaining,
        )

    def state_hash(self) -> str:
        """Return a deterministic hex digest of the current game state.

        Returns:
            8-character hex string.
        """
        canonical = json.dumps(self._state.to_dict(), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:8]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_move(self, actor: str, action: MoveAction) -> ActionResult:
        """Apply a directional move; update state and check win conditions."""
        s = self._state
        pos = s.cop_pos if actor == COP else s.thief_pos
        dc, dr = action.delta
        new_pos = (pos[0] + dc, pos[1] + dr)

        if not self._in_bounds(new_pos):
            return ActionResult(
                success=False,
                error=f"Move {action.direction} goes out of bounds to {new_pos}.",
                game_over=False, winner=None, win_reason=None,
            )
        if new_pos in s.barriers:
            return ActionResult(
                success=False,
                error=f"Cell {new_pos} is blocked by a barrier.",
                game_over=False, winner=None, win_reason=None,
            )

        if actor == COP:
            s.cop_pos = new_pos
        else:
            s.thief_pos = new_pos
            s.round += 1

        return self._finalize_turn(actor)

    def _apply_barrier(self, actor: str) -> ActionResult:
        """Place a barrier on cop's current cell (cop only)."""
        s = self._state

        if actor != COP:
            return ActionResult(
                success=False, error="Only the cop can place barriers.",
                game_over=False, winner=None, win_reason=None,
            )
        if s.barriers_placed >= s.max_barriers:
            return ActionResult(
                success=False, error="No barriers remaining.",
                game_over=False, winner=None, win_reason=None,
            )
        if s.cop_pos in s.barriers:
            return ActionResult(
                success=False, error="A barrier already exists on this cell.",
                game_over=False, winner=None, win_reason=None,
            )

        s.barriers.append(s.cop_pos)
        s.barriers_placed += 1
        # Barrier placement does NOT move the cop; it counts as the cop's turn.
        return self._finalize_turn(actor)

    def _finalize_turn(self, actor: str) -> ActionResult:
        """Check win conditions and return ActionResult after a successful action."""
        s = self._state

        # Capture: same cell after move
        if s.cop_pos == s.thief_pos:
            s.game_over = True
            s.winner = COP
            s.win_reason = WIN_CAPTURE
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=COP, win_reason=WIN_CAPTURE,
            )

        # Thief survived: round limit reached (thief's turn completes the round)
        if actor == THIEF and s.round >= s.max_moves:
            s.game_over = True
            s.winner = THIEF
            s.win_reason = WIN_THIEF_SURVIVED
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=THIEF, win_reason=WIN_THIEF_SURVIVED,
            )

        # Thief trapped: no legal moves on thief's next turn
        thief_moves = self._compute_legal_moves(THIEF)
        if not thief_moves:
            s.game_over = True
            s.winner = COP
            s.win_reason = WIN_THIEF_TRAPPED
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=COP, win_reason=WIN_THIEF_TRAPPED,
            )

        # Cop trapped: no legal moves AND no barriers remaining
        cop_moves = self._compute_legal_moves(COP)
        cop_has_barrier = (s.barriers_placed < s.max_barriers) and (s.cop_pos not in s.barriers)
        if not cop_moves and not cop_has_barrier:
            s.game_over = True
            s.winner = THIEF
            s.win_reason = WIN_COP_TRAPPED
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=THIEF, win_reason=WIN_COP_TRAPPED,
            )

        return ActionResult(
            success=True, error=None, game_over=False, winner=None, win_reason=None,
        )

    def _compute_legal_moves(self, actor: str) -> list[str]:
        """Return sorted list of legal action strings for the actor."""
        s = self._state
        pos = s.cop_pos if actor == COP else s.thief_pos
        moves = []
        for name in ALL_MOVE_ACTIONS:
            dc, dr = DIRECTIONS[name]
            target = (pos[0] + dc, pos[1] + dr)
            if self._in_bounds(target) and target not in s.barriers:
                moves.append(name)
        moves.sort()

        # Cop can also place a barrier if supply remains and cell is clear
        if actor == COP:
            can_barrier = (
                s.barriers_placed < s.max_barriers and pos not in s.barriers
            )
            if can_barrier:
                moves.append(BARRIER_ACTION)

        return moves

    def _in_bounds(self, pos: tuple[int, int]) -> bool:
        """Return True if pos is within the grid."""
        c, r = pos
        return 0 <= c < self._state.grid_cols and 0 <= r < self._state.grid_rows

    @staticmethod
    def _validate_position(
        pos: tuple[int, int], cols: int, rows: int, name: str
    ) -> None:
        """Raise ValueError if pos is outside the grid."""
        c, r = pos
        if not (0 <= c < cols and 0 <= r < rows):
            raise ValueError(
                f"{name} {pos} is outside grid ({cols}x{rows})"
            )

    # ------------------------------------------------------------------
    # Serialization (used by persistence layer)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return full state as a JSON-serializable dict."""
        return self._state.to_dict()

    @classmethod
    def from_dict(cls, d: dict) -> Game:
        """Restore a Game from a dict (loaded from state.json)."""
        return cls(GameState.from_dict(d))
