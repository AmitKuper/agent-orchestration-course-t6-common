"""Integration tests: full sub-game replays and retry flows (core Game class)."""

import json
import tempfile
from pathlib import Path

from game.constants import COP, THIEF
from game.game import Game
from game.persistence import load_state, save_state
from game.sdk import sdk


def test_full_game_cop_captures_thief() -> None:
    """Simulate a game where cop closes in and captures thief."""
    g = Game.new("integ1", (3, 3), (0, 0), (2, 2))
    results = [g.submit_action(a, act) for a, act in [(COP, "SE"), (THIEF, "NW")]]
    assert results[-1].game_over
    assert results[-1].winner == COP
    assert results[-1].win_reason == "capture"


def test_full_game_thief_survives() -> None:
    """Simulate a game where thief evades until max_moves."""
    g = Game.new("integ2", (5, 5), (0, 0), (4, 4), {"max_moves": 2})
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
    good = g.submit_action(COP, "E")
    assert good.success


def test_persist_and_resume() -> None:
    """Save mid-game state, reload, continue — outcome is same as continuous play."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        g = Game.new("integ4", (3, 3), (0, 0), (2, 2))
        g.submit_action(COP, "SE")
        save_state(g, base)
        g2 = load_state("integ4", base)
        result = g2.submit_action(THIEF, "NW")
        assert result.game_over
        assert result.winner == COP


def test_sdk_log_written_on_each_action() -> None:
    """SDK appends one JSONL line per submit_action call."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((5, 5), (0, 0), (4, 4), games_base=base)
        gid = info["game_id"]
        for actor, action in [(COP, "E"), (THIEF, "W"), (COP, "E")]:
            sdk.submit_action(gid, actor, action, games_base=base)
        lines = (base / gid / "game.log").read_text().splitlines()
        assert len(lines) == 3


def test_sdk_terminal_log_on_game_over() -> None:
    """SDK appends a terminal entry after the game-ending action."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
        gid = info["game_id"]
        sdk.submit_action(gid, COP, "SE", games_base=base)
        sdk.submit_action(gid, THIEF, "NW", games_base=base)  # capture

        lines = (base / gid / "game.log").read_text().splitlines()
        entries = [json.loads(ln) for ln in lines]
        terminal = entries[-1]
        assert terminal["type"] == "terminal"
        assert terminal["winner"] == "cop"
        assert terminal["win_reason"] == "capture"
        assert terminal["scores"] == {"cop": 20, "thief": 5}


def test_full_game_replay_from_log() -> None:
    """Replay a game from its log and reproduce the final state."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        info = sdk.new_game((3, 3), (0, 0), (2, 2), games_base=base)
        gid = info["game_id"]
        sdk.submit_action(gid, COP, "SE", games_base=base)
        sdk.submit_action(gid, THIEF, "NW", games_base=base)

        lines = (base / gid / "game.log").read_text().splitlines()
        # Filter out the terminal entry — replay only action entries
        actions = [json.loads(ln) for ln in lines if json.loads(ln).get("type") != "terminal"]

        g2 = Game.new("replay_check", (3, 3), (0, 0), (2, 2))
        final = None
        for entry in actions:
            act = "BARRIER" if entry["action"] == "barrier" else entry.get("direction", "SE")
            # For a move, reconstruct direction from from/to delta
            if entry["action"] == "move":
                dx = entry["to"][0] - entry["from"][0]
                dy = entry["to"][1] - entry["from"][1]
                from game.constants import DIRECTIONS
                act = next(k for k, v in DIRECTIONS.items() if v == (dx, dy))
            final = g2.submit_action(entry["actor"], act)

        assert final is not None
        assert final.game_over
        assert final.winner == COP
