"""Unit tests for the core Game state machine."""

import pytest

from game.constants import COP, THIEF
from game.game import Game


def make_game(
    grid: tuple[int, int] = (5, 5),
    cop: tuple[int, int] = (0, 0),
    thief: tuple[int, int] = (4, 4),
    mechanics: dict | None = None,
) -> Game:
    """Helper to create a standard test game."""
    return Game.new("test", grid, cop, thief, mechanics or {})


# ------------------------------------------------------------------
# Construction
# ------------------------------------------------------------------


def test_new_game_valid() -> None:
    """Game.new() succeeds with valid parameters."""
    g = make_game()
    assert g is not None


def test_new_game_off_grid_cop_raises() -> None:
    """Off-grid cop position raises ValueError."""
    with pytest.raises(ValueError, match="cop_pos"):
        Game.new("t", (5, 5), (5, 0), (4, 4))


def test_new_game_off_grid_thief_raises() -> None:
    """Off-grid thief position raises ValueError."""
    with pytest.raises(ValueError, match="thief_pos"):
        Game.new("t", (5, 5), (0, 0), (0, 5))


def test_new_game_same_pos_raises() -> None:
    """Identical positions raise ValueError."""
    with pytest.raises(ValueError, match="identical"):
        Game.new("t", (5, 5), (2, 2), (2, 2))


# ------------------------------------------------------------------
# Move validation
# ------------------------------------------------------------------


def test_move_all_directions() -> None:
    """All 8 directions succeed from centre of grid."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    for d in directions:
        g = Game.new("t", (5, 5), (2, 2), (0, 0))
        result = g.submit_action(COP, d)
        assert result.success, f"Direction {d} failed: {result.error}"


def test_move_out_of_bounds_north() -> None:
    """Move out of bounds to the north fails."""
    g = Game.new("t", (5, 5), (0, 0), (4, 4))
    result = g.submit_action(COP, "N")
    assert not result.success
    assert "out of bounds" in result.error.lower()


def test_move_into_barrier_fails() -> None:
    """Move into a barrier cell fails."""
    g = Game.new("t", (5, 5), (0, 0), (4, 4))
    # Place barrier at (1, 0) by hacking state for determinism
    g._state.barriers.append((1, 0))
    result = g.submit_action(COP, "E")
    assert not result.success
    assert "barrier" in result.error.lower()


def test_unknown_actor_fails() -> None:
    """Unknown actor returns error ActionResult."""
    g = make_game()
    result = g.submit_action("ghost", "N")
    assert not result.success
    assert "unknown actor" in result.error.lower()


def test_unknown_action_fails() -> None:
    """Unknown action string returns error ActionResult."""
    g = make_game()
    result = g.submit_action(COP, "JUMP")
    assert not result.success


# ------------------------------------------------------------------
# Barrier action
# ------------------------------------------------------------------


def test_cop_can_place_barrier() -> None:
    """Cop can place a barrier on current cell."""
    g = Game.new("t", (5, 5), (2, 2), (4, 4))
    result = g.submit_action(COP, "BARRIER")
    assert result.success
    assert (2, 2) in g._state.barriers


def test_thief_cannot_place_barrier() -> None:
    """Thief attempting BARRIER returns failure."""
    g = make_game()
    result = g.submit_action(THIEF, "BARRIER")
    assert not result.success
    assert "cop" in result.error.lower()


def test_barrier_limit_enforced() -> None:
    """Cop cannot place more barriers than max_barriers."""
    g = Game.new("t", (5, 5), (0, 0), (4, 4), {"max_barriers": 1})
    g.submit_action(COP, "BARRIER")
    # Move cop so next BARRIER cell is different
    g.submit_action(THIEF, "W")
    g.submit_action(COP, "E")
    result = g.submit_action(COP, "BARRIER")
    assert not result.success
    assert "no barriers remaining" in result.error.lower()


def test_no_double_barrier() -> None:
    """Cannot place a barrier on a cell that already has one."""
    g = Game.new("t", (5, 5), (2, 2), (4, 4))
    g.submit_action(COP, "BARRIER")
    # Cop is still at (2,2); try to place again
    result = g.submit_action(COP, "BARRIER")
    assert not result.success
    assert "already exists" in result.error.lower()


# ------------------------------------------------------------------
# get_state
# ------------------------------------------------------------------


def test_get_state_cop() -> None:
    """Cop observation contains barriers_remaining."""
    g = make_game()
    obs = g.get_state(COP)
    assert obs.actor == COP
    assert obs.barriers_remaining == 5


def test_get_state_thief() -> None:
    """Thief observation has barriers_remaining=None."""
    g = make_game()
    obs = g.get_state(THIEF)
    assert obs.actor == THIEF
    assert obs.barriers_remaining is None


def test_get_state_invalid_actor_raises() -> None:
    """get_state with unknown actor raises ValueError."""
    g = make_game()
    with pytest.raises(ValueError, match="Unknown actor"):
        g.get_state("ghost")


def test_legal_moves_exclude_barrier_for_thief() -> None:
    """BARRIER does not appear in thief's legal moves."""
    g = make_game()
    obs = g.get_state(THIEF)
    assert "BARRIER" not in obs.legal_moves


def test_legal_moves_include_barrier_for_cop() -> None:
    """BARRIER appears in cop's legal moves when supply remains."""
    g = make_game()
    obs = g.get_state(COP)
    assert "BARRIER" in obs.legal_moves


# ------------------------------------------------------------------
# state_hash
# ------------------------------------------------------------------


def test_state_hash_deterministic() -> None:
    """Same state always produces same hash."""
    g = make_game()
    assert g.state_hash() == g.state_hash()


def test_state_hash_changes_after_move() -> None:
    """Hash changes after a move."""
    g = make_game()
    h1 = g.state_hash()
    g.submit_action(COP, "E")
    assert g.state_hash() != h1
