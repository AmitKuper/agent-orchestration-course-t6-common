"""Sub-game series orchestration: retry logic and score accumulation."""

from __future__ import annotations

from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

from match_helpers import API_KEY, MAX_SG_RETRIES
from match_helpers.actor_game_loop import _actor_game_loop
from match_helpers.llm_game_loop import _game_loop
from match_helpers.log_reader import _count_rounds, _read_game_log, _read_terminal
from match_helpers.series_helpers import _propose_match, _sg_role
from match_helpers.servers import _derive_positions


async def _try_sub_game(
    sg_n: int, attempt: int, seed: int, grid: tuple[int, int],
    url_a: str, url_b: str, mode: str, game_type: str,
    max_rounds: int, turn_timeout: float, max_forfeits: int,
    time_debug: bool,
) -> dict | None:
    """Run one sub-game attempt; return result dict or None on technical loss.

    Args:
        sg_n: Sub-game number (1-based).
        attempt: Attempt number (1-based) for retry suffix.
        seed: Base seed for the series.
        grid: Grid dimensions.
        url_a: Server A base URL.
        url_b: Server B base URL.
        mode: "actor" or "llm".
        game_type: "internal" or "bonus".
        max_rounds: Orchestrator loop ceiling.
        turn_timeout: Per-tool-call timeout (actor mode).
        max_forfeits: Consecutive forfeit limit.
        time_debug: Emit per-phase timing when True.

    Returns:
        Sub-game result dict on success, None on technical loss.
    """
    sg_seed = seed + sg_n - 1
    sg_id = f"match{seed:04d}_sg{sg_n:02d}" + (f"_r{attempt}" if attempt > 1 else "")
    cop_pos, thief_pos = _derive_positions(sg_seed, grid)
    a_role = _sg_role(sg_n, game_type)
    b_role = "cop" if a_role == "thief" else "thief"
    match_args = {"game_id": sg_id, "seed": sg_seed,
                  "cop_pos": cop_pos, "thief_pos": thief_pos,
                  "grid_size": list(grid), "view_radius": 1, "max_moves": max_rounds}
    auth = BearerAuth(API_KEY)
    async with Client(url_b + "/mcp", auth=auth, timeout=30.0) as _cb:
        await _propose_match(_cb, {**match_args, "my_role": b_role, "initiator_url": url_a})
    async with Client(url_a + "/mcp", auth=auth, timeout=30.0) as _ca:
        await _propose_match(_ca, {**match_args, "my_role": a_role, "initiator_url": url_b})

    thief_url = url_a if a_role == "thief" else url_b
    cop_url = url_b if a_role == "thief" else url_a
    print(f"\n[sub-game {sg_n}/6  attempt {attempt}]  a={a_role} b={b_role}")
    result = (
        await _actor_game_loop(thief_url, cop_url, sg_id, max_rounds,
                               turn_timeout, max_forfeits, time_debug)
        if mode == "actor"
        else await _game_loop(thief_url, cop_url, sg_id, max_rounds)
    )
    if result.get("technical_loss"):
        retries_left = MAX_SG_RETRIES - attempt
        print(f"  TECHNICAL LOSS ({result.get('reason')}) — {retries_left} retries left")
        return None
    terminal = _read_terminal(sg_id)
    rounds = terminal.get("rounds") or _count_rounds(sg_id)
    if result.get("game_over"):
        winner = result.get("winner")
        win_reason = result.get("win_reason") or "thief_survived"
        cop_pts, thief_pts = (20, 5) if winner == "cop" else (5, 10)
    else:
        winner, win_reason, cop_pts, thief_pts = None, "incomplete", 0, 0
        print("  INCOMPLETE — round cap reached before game end (no score)")
    print(f"  winner={winner} ({win_reason})  rounds={rounds}")
    return {
        "sub_game": sg_n, "sg_id": sg_id, "initiator_role": a_role,
        "cop": "server_b" if a_role == "thief" else "server_a",
        "thief": "server_a" if a_role == "thief" else "server_b",
        "winner": winner, "win_reason": win_reason, "rounds": rounds,
        "barriers_used": terminal.get("barriers_used"),
        "scores": {"cop": cop_pts, "thief": thief_pts},
        "log": _read_game_log(sg_id),
    }


async def _run_series(
    url_a: str, url_b: str, mode: str, seed: int,
    max_rounds: int, game_type: str, grid: tuple[int, int],
    turn_timeout: float = 30.0, max_forfeits: int = 3,
    num_games: int = 6, view_radius: int = 1, max_moves: int = 25,
    time_debug: bool = False,
) -> list[dict]:
    """Run num_games valid sub-games, re-running on technical loss.

    Args:
        url_a: Server A base URL.
        url_b: Server B base URL.
        mode: "actor" or "llm".
        seed: Base seed; sub-game n uses seed + n - 1.
        max_rounds: Per-sub-game orchestrator loop ceiling.
        game_type: "internal" or "bonus".
        grid: Grid dimensions.
        turn_timeout: Per-tool-call timeout (actor mode).
        max_forfeits: Consecutive forfeit limit.
        num_games: Number of valid sub-games to play.
        view_radius: Chebyshev visibility radius (passed to propose_match).
        max_moves: Engine-level round cap.
        time_debug: Emit per-phase timing per turn when True.

    Returns:
        List of sub-game result dicts for the report.
    """
    sub_games: list[dict] = []
    sg_n = 1
    while sg_n <= num_games:
        entry = None
        for attempt in range(1, MAX_SG_RETRIES + 1):
            entry = await _try_sub_game(
                sg_n, attempt, seed, grid, url_a, url_b,
                mode, game_type, max_rounds, turn_timeout, max_forfeits, time_debug,
            )
            if entry is not None:
                break
        if entry is None:
            print(f"  Sub-game {sg_n} exhausted {MAX_SG_RETRIES} retries — recording void.")
            entry = {
                "sub_game": sg_n, "initiator_role": _sg_role(sg_n, game_type),
                "winner": None, "win_reason": "technical_loss",
                "scores": {"cop": 0, "thief": 0},
            }
        sub_games.append(entry)
        sg_n += 1
    return sub_games
