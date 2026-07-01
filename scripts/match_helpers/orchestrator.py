"""Async main orchestrator: configure, start servers, run series, report."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from match_helpers import LOOP_CAP_MARGIN, MAX_FORFEIT_STREAK, REPO_ROOT
from match_helpers.notifier import _fetch_player_info, _maybe_send_report
from match_helpers.series import _run_series
from match_helpers.servers import (
    _load_config,
    _start_servers,
    _wait_for_server,
    build_server_envs,
)


async def _async_main(
    seed: int, max_rounds: int | None, mode: str, actor_class: str,
    models_dir: str, game_type: str, num_games: int = 6,
    opponent_url: str = "", local_url: str = "",
    port_a: int = 8001, port_b: int = 8002,
    time_debug: bool = False,
) -> None:
    """Start servers, run the sub-game series, print totals, send report.

    Args:
        seed: Random seed for position derivation.
        max_rounds: Orchestrator round cap (overrides config max_moves when set).
        mode: "actor" or "llm".
        actor_class: Dotted class path for the actor (actor mode).
        models_dir: Directory containing cop/thief Q-table files.
        game_type: "internal" or "bonus".
        num_games: Number of valid sub-games to play.
        opponent_url: External opponent URL — skips starting server B.
        local_url: URL of an already-running server A — skips starting it.
        port_a: Port for server A.
        port_b: Port for server B.
        time_debug: If True, emit per-phase timing per turn.
    """
    cfg = _load_config()
    grid_cfg = cfg.get("grid_size", [5, 5])
    grid = (grid_cfg[0], grid_cfg[1])
    turn_timeout = float(cfg.get("turn_timeout_seconds", 30))
    max_forfeits = int(cfg.get("max_consecutive_forfeits", MAX_FORFEIT_STREAK))
    num_games = num_games or int(cfg.get("num_games", 6))
    view_radius = int(cfg.get("view_radius", 1))
    max_moves = max_rounds if max_rounds is not None else int(cfg.get("max_moves", 25))
    loop_cap = max_moves + LOOP_CAP_MARGIN
    series_id = f"series{seed:04d}"
    print(f"[match] seed={seed} series_id={series_id} mode={mode} game_type={game_type}")

    for _env_key in ("GMAIL_TOKEN_PATH", "GMAIL_CREDENTIALS_PATH"):
        _val = os.environ.get(_env_key, "")
        if _val and not Path(_val).is_absolute():
            os.environ[_env_key] = str((REPO_ROOT / _val).resolve())

    player_a = os.environ.get("PLAYER_NAME", "Player A")
    player_b = os.environ.get("OPPONENT_PLAYER_NAME", "Player B")

    if opponent_url and not opponent_url.startswith("http"):
        opponent_url = "http://" + opponent_url
    url_b = opponent_url or f"http://localhost:{port_b}"

    env_a, env_b = build_server_envs(
        mode, actor_class, models_dir, url_b, port_a, player_a, player_b,
    )

    attach_mode = bool(local_url)
    single = bool(opponent_url)
    if attach_mode:
        proc_a, proc_b = None, None
        url_a = local_url if local_url.startswith("http") else "http://" + local_url
    else:
        proc_a, proc_b = _start_servers(
            env_a, env_b, sys.executable, single=single, port_a=port_a, port_b=port_b,
        )
        url_a = f"http://localhost:{port_a}"
    try:
        print("[match] waiting for servers...")
        if not attach_mode:
            _wait_for_server(url_a)
        if not single:
            _wait_for_server(url_b)
        print(f"[match] server(s) up — opponent: {url_b}")

        player_b, _ = await _fetch_player_info(url_b, player_b)
        print(f"[match] players: {player_a} vs {player_b}")

        sub_games = await _run_series(
            url_a, url_b, mode, seed, loop_cap, game_type, grid,
            turn_timeout, max_forfeits, num_games, view_radius, max_moves, time_debug,
        )

        cop_total = sum(sg["scores"]["cop"] for sg in sub_games)
        thief_total = sum(sg["scores"]["thief"] for sg in sub_games)
        print(f"\n[series] totals: cop={cop_total}  thief={thief_total}")
        _maybe_send_report(sub_games, series_id, game_type)
    finally:
        if proc_a:
            proc_a.terminate()
            proc_a.wait()
        if proc_b:
            proc_b.terminate()
            proc_b.wait()
        print("[match] servers stopped")
