"""GameRules mixin — move validation, action application, and win detection.

Extracted from Game to keep each file under 150 lines. Inherit via Game only.
"""

from __future__ import annotations

from game.actions import MoveAction
from game.constants import (
    ALL_MOVE_ACTIONS,
    BARRIER_ACTION,
    COP,
    DIRECTIONS,
    STAY_ACTION,
    THIEF,
    WIN_CAPTURE,
    WIN_COP_TRAPPED,
    WIN_THIEF_SURVIVED,
    WIN_THIEF_TRAPPED,
)
from game.game_state import GameState
from game.state import ActionResult


class GameRules:
    """Mixin providing internal game logic for the Game class."""

    _state: GameState  # provided by Game.__init__

    def _apply_move(self, actor: str, action: MoveAction) -> ActionResult:
        """Apply a directional move; update position and check win conditions."""
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

    def _apply_stay(self) -> ActionResult:
        """Thief stays in place for one turn without changing position."""
        self._state.round += 1
        return self._finalize_turn(THIEF)

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
        return self._finalize_turn(actor)

    def _finalize_turn(self, actor: str) -> ActionResult:
        """Increment turn counter, check win conditions, return ActionResult."""
        s = self._state
        s.turn += 1

        if s.cop_pos == s.thief_pos:
            s.game_over, s.winner, s.win_reason = True, COP, WIN_CAPTURE
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=COP, win_reason=WIN_CAPTURE,
            )

        if actor == THIEF and s.round >= s.max_moves:
            s.game_over, s.winner, s.win_reason = True, THIEF, WIN_THIEF_SURVIVED
            return ActionResult(
                success=True, error=None, game_over=True,
                winner=THIEF, win_reason=WIN_THIEF_SURVIVED,
            )

        # Thief can always STAY, so WIN_THIEF_TRAPPED is not reachable.

        cop_moves = self._compute_legal_moves(COP)
        can_barrier = s.barriers_placed < s.max_barriers and s.cop_pos not in s.barriers
        if not cop_moves and not can_barrier:
            s.game_over, s.winner, s.win_reason = True, THIEF, WIN_COP_TRAPPED
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
        moves = [
            name for name in ALL_MOVE_ACTIONS
            if self._in_bounds((pos[0] + DIRECTIONS[name][0], pos[1] + DIRECTIONS[name][1]))
            and (pos[0] + DIRECTIONS[name][0], pos[1] + DIRECTIONS[name][1]) not in s.barriers
        ]
        moves.sort()
        if actor == COP and s.barriers_placed < s.max_barriers and pos not in s.barriers:
            moves.append(BARRIER_ACTION)
        if actor == THIEF:
            moves.append(STAY_ACTION)
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
            raise ValueError(f"{name} {pos} is outside grid ({cols}x{rows})")
