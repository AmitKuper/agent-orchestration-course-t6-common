"""Game constants: directions, actors, win reasons, and defaults."""

from __future__ import annotations

# 8-direction move deltas: (col_delta, row_delta)
DIRECTIONS: dict[str, tuple[int, int]] = {
    "N": (0, -1),
    "NE": (1, -1),
    "E": (1, 0),
    "SE": (1, 1),
    "S": (0, 1),
    "SW": (-1, 1),
    "W": (-1, 0),
    "NW": (-1, -1),
}

BARRIER_ACTION = "BARRIER"

ALL_MOVE_ACTIONS: frozenset[str] = frozenset(DIRECTIONS.keys())
ALL_ACTIONS: frozenset[str] = ALL_MOVE_ACTIONS | {BARRIER_ACTION}

# Actor names
COP = "cop"
THIEF = "thief"
ACTORS: frozenset[str] = frozenset({COP, THIEF})

# Win reasons
WIN_CAPTURE = "capture"
WIN_THIEF_TRAPPED = "thief_trapped"
WIN_COP_TRAPPED = "cop_trapped"
WIN_THIEF_SURVIVED = "thief_survived"

# Game defaults
DEFAULT_GRID_SIZE: tuple[int, int] = (5, 5)
DEFAULT_MAX_MOVES: int = 30
DEFAULT_MAX_BARRIERS: int = 5

# Scoring defaults (PRD §4 / §5)
SCORE_COP_WIN: int = 20    # cop captures or thief_trapped
SCORE_THIEF_WIN: int = 10  # thief survives or cop_trapped
SCORE_COP_LOSS: int = 5    # cop's points when thief wins
SCORE_THIEF_LOSS: int = 5  # thief's points when cop wins


def compute_scores(winner: str, mechanics: dict) -> dict[str, int]:
    """Return per-actor scores for this sub-game outcome.

    Args:
        winner: "cop" or "thief".
        mechanics: Game mechanics dict (may contain a "scoring" sub-dict).

    Returns:
        Dict with "cop" and "thief" integer point values.
    """
    sc = mechanics.get("scoring", {})
    cop_win = int(sc.get("cop_win", SCORE_COP_WIN))
    thief_win = int(sc.get("thief_win", SCORE_THIEF_WIN))
    cop_loss = int(sc.get("cop_loss", SCORE_COP_LOSS))
    thief_loss = int(sc.get("thief_loss", SCORE_THIEF_LOSS))
    if winner == COP:
        return {"cop": cop_win, "thief": thief_loss}
    return {"cop": cop_loss, "thief": thief_win}
