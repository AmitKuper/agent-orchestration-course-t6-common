"""Server startup, health-check, and environment helpers for run_match.py."""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from pathlib import Path

import httpx

from match_helpers import API_KEY, REPO_ROOT


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    """Poll /health until the server responds or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url + "/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not start within {timeout}s")


def _derive_positions(seed: int, grid: tuple[int, int]) -> tuple[list[int], list[int]]:
    """Derive cop and thief start positions deterministically from seed."""
    rng = random.Random(seed)
    cols, rows = grid
    cop = [rng.randrange(cols), rng.randrange(rows)]
    thief = cop[:]
    while thief == cop:
        thief = [rng.randrange(cols), rng.randrange(rows)]
    return cop, thief


def _start_servers(
    env_a: dict, env_b: dict, python: str,
    single: bool = False, port_a: int = 8001, port_b: int = 8002,
) -> tuple:
    """Launch server A and optionally server B on configurable ports.

    Args:
        env_a: Environment for server A.
        env_b: Environment for server B (ignored when single=True).
        python: Python executable path.
        single: If True, only start server A (opponent is external).
        port_a: Port for server A.
        port_b: Port for server B.

    Returns:
        (proc_a, proc_b) — proc_b is None when single=True.
    """
    mod = "game.wrappers.mcp_server"
    cwd = str(REPO_ROOT)
    proc_a = subprocess.Popen(
        [python, "-m", mod, "--port", str(port_a), "--games-dir", f"games/server_{port_a}"],
        env=env_a, cwd=cwd,
    )
    if single:
        return proc_a, None
    proc_b = subprocess.Popen(
        [python, "-m", mod, "--port", str(port_b), "--games-dir", f"games/server_{port_b}"],
        env=env_b, cwd=cwd,
    )
    return proc_a, proc_b


def _load_config() -> dict:
    """Load game configuration from config/config.json (empty dict if missing)."""
    cfg_path = REPO_ROOT / "config" / "config.json"
    if cfg_path.exists():
        with cfg_path.open() as fh:
            return json.load(fh)
    return {}


def build_server_envs(
    mode: str, actor_class: str, models_dir: str,
    url_b: str, port_a: int, player_a: str, player_b: str,
) -> tuple[dict, dict]:
    """Build environment dicts for server A and server B.

    Args:
        mode: "actor" or "llm".
        actor_class: Dotted class path (actor mode only).
        models_dir: Directory with .npy Q-table files.
        url_b: URL of server B.
        port_a: Port of server A (for B's OPPONENT_MCP_URL).
        player_a: Display name for server A.
        player_b: Display name for server B.

    Returns:
        (env_a, env_b) dicts ready to pass to subprocess.Popen.
    """
    env_a = {**os.environ, "OPPONENT_MCP_URL": url_b,
             "MCP_API_KEY": API_KEY, "MCP_ALLOWED_API_KEYS": API_KEY,
             "PLAYER_NAME": player_a}
    env_b = {**os.environ, "OPPONENT_MCP_URL": f"http://localhost:{port_a}",
             "MCP_API_KEY": API_KEY, "MCP_ALLOWED_API_KEYS": API_KEY,
             "PLAYER_NAME": player_b}
    if mode == "actor":
        mdir = Path(models_dir) if Path(models_dir).is_absolute() else Path.cwd() / models_dir
        parent_src = str(REPO_ROOT.parent / "src")
        existing = os.environ.get("PYTHONPATH", "")
        extra = parent_src + (os.pathsep + existing if existing else "")
        tables = {"COP_ACTOR_TABLE": str(mdir / "cop_qtable.npy"),
                  "THIEF_ACTOR_TABLE": str(mdir / "thief_qtable.npy")}
        env_a = {**env_a, "ACTOR_CLASS": actor_class, **tables, "PYTHONPATH": extra}
        env_b = {**env_b, "ACTOR_CLASS": actor_class, **tables, "PYTHONPATH": extra}
    return env_a, env_b
