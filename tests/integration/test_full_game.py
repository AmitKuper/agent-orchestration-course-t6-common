"""Integration tests: full sub-game replays and retry flows."""

import json
import tempfile
from pathlib import Path

from game.constants import COP, THIEF
from game.game import Game
from game.persistence import append_log, load_state, save_state


def test_full_game_cop_captures_thief() -> None:
    """Simulate a game where cop closes in and captures thief."""
    g = Game.new("integ1", (3, 3), (0, 0), (2, 2))

    moves = [
        (COP, "SE"),
        (THIEF, "NW"),  # thief moves toward cop
    ]
    # After cop SE: cop=(1,1), thief=(2,2)
    # After thief NW: cop=(1,1), thief=(1,1) → capture
    results = []
    for actor, action in moves:
        result = g.submit_action(actor, action)
        results.append(result)

    assert results[-1].game_over
    assert results[-1].winner == COP
    assert results[-1].win_reason == "capture"


def test_full_game_thief_survives() -> None:
    """Simulate a game where thief evades until max_moves."""
    g = Game.new("integ2", (5, 5), (0, 0), (4, 4), {"max_moves": 2})
    # Cop and thief bounce; neither captures
    g.submit_action(COP, "E")
    g.submit_action(THIEF, "W")
    g.submit_action(COP, "W")
    result = g.submit_action(THIEF, "E")
    assert result.game_over
    assert result.winner == THIEF
    assert result.win_reason == "thief_survived"


def test_illegal_move_retry_flow() -> None:
    """Agent receives error, retries with valid action — game continues."""
    g = Game.new("integ3", (5, 5), (0, 0), (4, 4))
    bad = g.submit_action(COP, "N")   # off grid from (0,0)
    assert not bad.success
    assert not bad.game_over

    good = g.submit_action(COP, "E")  # valid retry
    assert good.success


def test_persist_and_resume() -> None:
    """Save mid-game state, reload, continue — outcome is the same as continuous play."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        g = Game.new("integ4", (3, 3), (0, 0), (2, 2))

        g.submit_action(COP, "SE")
        save_state(g, base)

        g2 = load_state("integ4", base)
        result = g2.submit_action(THIEF, "NW")  # capture

        assert result.game_over
        assert result.winner == COP


def test_log_written_on_each_action() -> None:
    """Each submit_action call produces a log entry when caller appends."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        g = Game.new("integ5", (5, 5), (0, 0), (4, 4))

        for actor, action in [(COP, "E"), (THIEF, "W"), (COP, "E")]:
            result = g.submit_action(actor, action)
            append_log("integ5", actor, action, result, base=base)
            save_state(g, base)

        lines = (base / "integ5" / "game.log").read_text().splitlines()
        assert len(lines) == 3


def test_full_game_replay_from_log() -> None:
    """Replay a game from its log and reproduce the final state."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        g = Game.new("replay", (3, 3), (0, 0), (2, 2))
        transcript = [(COP, "SE"), (THIEF, "NW")]
        for actor, action in transcript:
            result = g.submit_action(actor, action)
            append_log("replay", actor, action, result, base=base)
        save_state(g, base)

        lines = (base / "replay" / "game.log").read_text().splitlines()
        entries = [json.loads(line) for line in lines]

        g2 = Game.new("replay_check", (3, 3), (0, 0), (2, 2))
        final = None
        for entry in entries:
            final = g2.submit_action(entry["actor"], entry["action"])

        assert final is not None
        assert final.game_over
        assert final.winner == COP
