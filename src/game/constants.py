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
