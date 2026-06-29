"""State hash helper extracted from Game to keep game.py under 150 lines."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.game_state import GameState


def compute_state_hash(state: GameState) -> str:
    """Return an 8-char deterministic hex digest of the gameplay state.

    Excludes administrative fields (game_id, mechanics, max_moves, max_barriers,
    grid size) that can legitimately differ between server versions without
    indicating a real state divergence.

    Args:
        state: Current GameState snapshot.

    Returns:
        8-character hex string.
    """
    canonical = json.dumps({
        "cop_pos": list(state.cop_pos),
        "thief_pos": list(state.thief_pos),
        "barriers": sorted(list(b) for b in state.barriers),
        "round": state.round,
        "turn": state.turn,
        "barriers_placed": state.barriers_placed,
        "game_over": state.game_over,
        "winner": state.winner,
        "win_reason": state.win_reason,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]
