"""Unit tests for Game win conditions (capture, survival, trapped)."""

from game.constants import COP, THIEF
from game.game import Game


def test_capture_win() -> None:
    """Cop lands on thief's cell → cop wins by capture."""
    g = Game.new("t", (5, 5), (3, 4), (4, 4))
    result = g.submit_action(COP, "E")
    assert result.game_over
    assert result.winner == COP
    assert result.win_reason == "capture"


def test_thief_survived_win() -> None:
    """Thief survives max_moves rounds → thief wins."""
    g = Game.new("t", (5, 5), (0, 0), (4, 4), {"max_moves": 1})
    g.submit_action(COP, "E")
    result = g.submit_action(THIEF, "W")
    assert result.game_over
    assert result.winner == THIEF
    assert result.win_reason == "thief_survived"


def test_thief_surrounded_can_stay() -> None:
    """Thief with all neighbours barriered still has STAY as a legal move."""
    g = Game.new("t", (3, 3), (0, 0), (2, 2))
    for pos in [(1, 1), (2, 1), (1, 2)]:
        g._state.barriers.append(pos)
    obs = g.get_state(THIEF)
    assert obs.legal_moves == ["STAY"]
    result = g.submit_action(THIEF, "STAY")
    assert result.success
    assert not result.game_over


def test_game_over_rejects_further_actions() -> None:
    """Actions after game over return failure."""
    g = Game.new("t", (5, 5), (3, 4), (4, 4))
    g.submit_action(COP, "E")  # capture
    result = g.submit_action(THIEF, "W")
    assert not result.success
    assert "already over" in result.error.lower()
