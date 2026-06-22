"""Integration tests: full games played through the CLI wrapper.

Each test invokes 'python -m game <command>' as a subprocess, mimicking
exactly what a human operator or shell script would do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Use the project venv Python so the subprocess has access to the `game` package.
# uv run pytest may inject packages via PYTHONPATH rather than setting sys.executable
# to the venv Python, so subprocess tests must resolve the venv interpreter explicitly.
_REPO_ROOT = Path(__file__).parents[2]
_IS_WIN = sys.platform == "win32"
_VENV_PYTHON = _REPO_ROOT / ".venv" / ("Scripts" if _IS_WIN else "bin") / (
    "python.exe" if _IS_WIN else "python"
)
# Fall back to sys.executable if the venv isn't present (e.g. CI with system install).
_PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


def _run(*args: str, games_dir: str) -> subprocess.CompletedProcess:
    """Invoke 'python -m game <args>' with an isolated games directory."""
    return subprocess.run(
        [_PYTHON, "-m", "game", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "GAMES_DIR": games_dir},
    )


def _new_game(grid: str, cop: str, thief: str, games_dir: str) -> str:
    """Create a game via CLI and return game_id."""
    r = _run("new", "--grid", grid, "--cop", cop, "--thief", thief, games_dir=games_dir)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["game_id"]


def test_cli_new_game_returns_game_id() -> None:
    """CLI 'new' returns a JSON object with a non-empty game_id."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run("new", "--grid", "5,5", "--cop", "0,0", "--thief", "4,4", games_dir=tmp)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "game_id" in data
        assert len(data["game_id"]) == 8


def test_cli_new_invalid_position_exits_nonzero() -> None:
    """CLI 'new' with off-grid cop exits non-zero and writes to stderr."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run("new", "--grid", "5,5", "--cop", "9,9", "--thief", "4,4", games_dir=tmp)
        assert r.returncode != 0
        assert r.stderr.strip() != ""


def test_cli_submit_valid_move() -> None:
    """CLI 'submit' returns success JSON with exit code 0."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        r = _run("submit", gid, "--actor", "cop", "--action", "E", games_dir=tmp)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["success"] is True
        assert data["game_over"] is False


def test_cli_submit_illegal_move_exits_1() -> None:
    """CLI 'submit' with off-grid move exits 1 and returns failure JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        r = _run("submit", gid, "--actor", "cop", "--action", "N", games_dir=tmp)
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["success"] is False


def test_cli_submit_capture_exits_2() -> None:
    """CLI 'submit' that ends the game exits 2."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("3,3", "0,0", "2,2", tmp)
        _run("submit", gid, "--actor", "cop", "--action", "SE", games_dir=tmp)
        r = _run("submit", gid, "--actor", "thief", "--action", "NW", games_dir=tmp)
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["game_over"] is True
        assert data["winner"] == "cop"


def test_cli_get_state_returns_observation() -> None:
    """CLI 'get-state' returns a valid ObservationState JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        r = _run("get-state", gid, "--actor", "cop", games_dir=tmp)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["actor"] == "cop"
        assert "my_pos" in data
        assert "legal_moves" in data
        assert "barriers_remaining" in data


def test_cli_get_state_thief_no_barriers_remaining() -> None:
    """CLI 'get-state' for thief has barriers_remaining=null."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        r = _run("get-state", gid, "--actor", "thief", games_dir=tmp)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["barriers_remaining"] is None


def test_cli_hash_returns_hex_string() -> None:
    """CLI 'hash' returns JSON with an 8-char hex hash."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        r = _run("hash", gid, games_dir=tmp)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "hash" in data
        assert len(data["hash"]) == 8
        int(data["hash"], 16)  # valid hex


def test_cli_full_game_sequence() -> None:
    """CLI: play a complete game from new → submit → capture via subprocesses."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("3,3", "0,0", "2,2", tmp)

        r1 = _run("submit", gid, "--actor", "cop", "--action", "SE", games_dir=tmp)
        assert r1.returncode == 0

        r2 = _run("submit", gid, "--actor", "thief", "--action", "NW", games_dir=tmp)
        assert r2.returncode == 2  # game over
        data = json.loads(r2.stdout)
        assert data["winner"] == "cop"
        assert data["win_reason"] == "capture"


def test_cli_state_updates_after_move() -> None:
    """CLI: cop position in get-state reflects the last move."""
    with tempfile.TemporaryDirectory() as tmp:
        gid = _new_game("5,5", "0,0", "4,4", tmp)
        _run("submit", gid, "--actor", "cop", "--action", "E", games_dir=tmp)
        r = _run("get-state", gid, "--actor", "cop", games_dir=tmp)
        data = json.loads(r.stdout)
        assert data["my_pos"] == [1, 0]


def test_cli_unknown_game_id_exits_nonzero() -> None:
    """CLI 'submit' with non-existent game_id exits non-zero."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _run("submit", "badid", "--actor", "cop", "--action", "E", games_dir=tmp)
        assert r.returncode != 0
        assert r.stderr.strip() != ""
