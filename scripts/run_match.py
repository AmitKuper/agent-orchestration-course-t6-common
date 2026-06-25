"""Orchestrate a full 6-sub-game series between two local MCP servers.

Architecture (PRD §6): the LLM lives in this orchestrator — not inside the MCP servers.
For actor mode: get_actor_action (Q-table) → LLM message here → take_action.
For llm mode: ToolCaller lets the LLM call get_state then take_action.

Usage:
    python scripts/run_match.py [--seed SEED] [--max-rounds 30] [--mode actor|llm]
                                [--game-type internal|bonus]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import subprocess
import sys

# Force UTF-8 output so emoji/non-ASCII in opponent messages don't crash on
# Windows consoles that default to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.auth.bearer import BearerAuth

_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(_REPO_ROOT / ".env")
_API_KEY = os.environ.get("MCP_API_KEY", "demo-key")

_SYSTEM_COP = (
    "You are the COP in a 5×5 Cop & Thief grid game. "
    "Capture the thief by landing on its cell. "
    "You may move N NE E SE S SW W NW or place BARRIER on your cell (max 5). "
    "Call get_state to observe the board, then take_action with your move "
    "and a one-sentence message."
)
_SYSTEM_THIEF = (
    "You are the THIEF in a 5×5 Cop & Thief grid game. "
    "Survive 25 rounds without being captured. "
    "You may move N NE E SE S SW W NW. No barriers. "
    "Call get_state to observe the board, then take_action with your move "
    "and a one-sentence message."
)
_DIRS: dict[str, str] = {
    "N": "north", "NE": "northeast", "E": "east", "SE": "southeast",
    "S": "south", "SW": "southwest", "W": "west", "NW": "northwest",
    "BARRIER": "barrier on current cell",
}
_MAX_FORFEIT_STREAK = 3   # consecutive actor errors before technical loss
_MAX_SG_RETRIES = 3       # max re-runs per sub-game on technical loss


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    """Poll the health endpoint until the server responds or timeout expires."""
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
        port_a: Port for server A (default 8001).
        port_b: Port for server B (default 8002).

    Returns:
        (proc_a, proc_b) — proc_b is None when single=True.
    """
    mod = "game.wrappers.mcp_server"
    cwd = str(_REPO_ROOT)
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
    cfg_path = _REPO_ROOT / "config" / "config.json"
    if cfg_path.exists():
        with cfg_path.open() as fh:
            return json.load(fh)
    return {}


def _read_terminal(sg_id: str) -> dict:
    """Read the terminal log entry for sg_id from server_a or server_b game log."""
    for server in ("server_a", "server_b"):
        log_path = _REPO_ROOT / "games" / server / sg_id / "game.log"
        if log_path.exists():
            for raw in reversed(log_path.read_text().splitlines()):
                if raw.strip():
                    entry = json.loads(raw)
                    if entry.get("type") == "terminal":
                        return entry
    return {}


async def _agent_turn(
    caller: object, client: Client, game_id: str, actor: str, system: str,
) -> dict:
    """Run one LLM tool-use turn: the model calls get_state then take_action.

    Args:
        caller: ToolCaller instance driving the LLM loop.
        client: FastMCP Client connected to the relevant server.
        game_id: Active game identifier.
        actor: "cop" or "thief".
        system: System prompt grounding the agent in its role.

    Returns:
        Parsed ActionResult dict from the take_action tool call.
    """
    from game.wrappers.mcp_agent_tools import GAME_TOOLS

    last_result: dict = {}

    async def executor(name: str, args: dict) -> str:
        """Execute a tool call via the MCP client and capture take_action results."""
        nonlocal last_result
        tool_result = await client.call_tool(name, args)
        text = tool_result.content[0].text if tool_result.content else "{}"
        if name == "take_action":
            last_result = json.loads(text)
        return text

    prompt = (
        f"Take your turn as {actor} in game {game_id}. "
        "First call get_state to see the board, then call take_action with your move."
    )
    await caller.call_with_tools(
        [{"role": "user", "content": prompt}], GAME_TOOLS, executor, system=system,
    )
    return last_result


def _tech_loss(reason: str) -> dict:
    """Return a technical-loss sentinel dict."""
    return {"technical_loss": True, "reason": reason}


async def _propose_match(client: object, args: dict) -> None:
    """Call propose_match_tool, stripping optional keys if the remote rejects them.

    Older server versions don't accept view_radius or initiator_url.
    """
    from fastmcp.exceptions import ToolError
    _optional = ("view_radius", "initiator_url", "max_moves")
    try:
        await client.call_tool("propose_match_tool", args)
    except ToolError as exc:
        err = str(exc)
        if "unexpected" in err.lower() and any(k in err for k in _optional):
            stripped = {k: v for k, v in args.items() if k not in _optional}
            await client.call_tool("propose_match_tool", stripped)
        else:
            raise


def _board_str(sg_id: str) -> str:
    """Return a compact ASCII board string from the latest game log entry."""
    for server in ("server_a", "server_b"):
        log_path = _REPO_ROOT / "games" / server / sg_id / "game.log"
        if not log_path.exists():
            continue
        for raw in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if not raw.strip():
                continue
            e = json.loads(raw)
            if e.get("type") != "turn" or "state_after" not in e:
                continue
            sa = e["state_after"]
            cols, rows = 5, 5
            barriers = {tuple(b) for b in sa.get("barriers", [])}
            cop = tuple(sa["cop"])
            thief = tuple(sa["thief"])
            lines = ["  " + " ".join(str(c) for c in range(cols))]
            for r in range(rows):
                row = [str(r)]
                for c in range(cols):
                    cell = (c, r)
                    if cell == cop and cell == thief:
                        row.append("X")
                    elif cell == cop:
                        row.append("C")
                    elif cell == thief:
                        row.append("T")
                    elif cell in barriers:
                        row.append("#")
                    else:
                        row.append(".")
                lines.append(" ".join(row))
            return "\n".join(lines)
    return ""


async def _actor_turn(
    client: object, actor: str, game_id: str,
    gk: object, system: str, timeout: float,
    opponent_msg: str = "",
) -> dict:
    """Execute one actor turn: get_actor_action → contextual NL message → take_action.

    Args:
        client: FastMCP Client connected to the actor's server.
        actor: "cop" or "thief".
        game_id: Active game identifier.
        gk: Gatekeeper instance for LLM calls.
        system: System prompt for NL message generation.
        timeout: Per-tool-call timeout in seconds.
        opponent_msg: The opponent's last NL message, for contextual response.

    Returns:
        ActionResult dict with "_msg" key for the sent message,
        or {"forfeit": True, "reason": ...} on timeout/error.
    """
    try:
        ar = await asyncio.wait_for(
            client.call_tool("get_actor_action", {"game_id": game_id, "actor": actor}),
            timeout=timeout,
        )
        adata = json.loads(ar.content[0].text if ar.content else "{}")
        if "error" in adata:
            return {"forfeit": True, "reason": adata["error"]}
        action = adata["action"]
        direction = _DIRS.get(action, action.lower())
        if opponent_msg:
            prompt = (
                f"You are the {actor.upper()} in a cop-thief pursuit game. "
                f"Opponent's last message: '{opponent_msg}'. "
                f"You chose to move {direction}. "
                "In one sentence describe your move."
            )
        else:
            prompt = (
                f"You are the {actor.upper()} in a cop-thief pursuit game "
                f"and you are moving {direction}. "
                "In one sentence describe your intent."
            )
        msg = await asyncio.to_thread(gk.call, [{"role": "user", "content": prompt}], system)
        tr = await asyncio.wait_for(
            client.call_tool(
                "take_action",
                {"game_id": game_id, "actor": actor, "action": action, "message": msg.strip()},
            ),
            timeout=timeout,
        )
        result = json.loads(tr.content[0].text if tr.content else "{}")
        if not result.get("success", True):
            return {"forfeit": True, "reason": "illegal_action"}
        result["_msg"] = msg.strip()
        result["_action"] = action
        return result
    except TimeoutError:
        return {"forfeit": True, "reason": "timeout"}


async def _actor_game_loop(
    url_a: str, url_b: str, game_id: str, max_rounds: int,
    turn_timeout: float = 30.0, max_forfeits: int = 3,
) -> dict:
    """Drive turns via _actor_turn (Q-table → NL message → take_action) per PRD §6.

    Returns:
        Final ActionResult dict, or a technical-loss sentinel on engine divergence.
    """
    from game.shared.gatekeeper import Gatekeeper

    gk = Gatekeeper(model=os.environ.get("LLM_MODEL") or None)
    auth = BearerAuth(_API_KEY)
    last_result: dict = {}
    consec_forfeits: dict[str, int] = {"thief": 0, "cop": 0}
    last_messages: dict[str, str] = {"thief": "", "cop": ""}

    async with Client(url_a + "/mcp", auth=auth, timeout=turn_timeout) as ca, \
               Client(url_b + "/mcp", auth=auth, timeout=turn_timeout) as cb:
        game_over, round_num = False, 0
        while not game_over and round_num < max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for client, actor, system in [
                (ca, "thief", _SYSTEM_THIEF),
                (cb, "cop", _SYSTEM_COP),
            ]:
                other = cb if client is ca else ca
                opponent = "cop" if actor == "thief" else "thief"
                result = await _actor_turn(
                    client, actor, game_id, gk, system, turn_timeout,
                    opponent_msg=last_messages[opponent],
                )
                if result.get("forfeit"):
                    consec_forfeits[actor] += 1
                    if consec_forfeits[actor] >= max_forfeits:
                        return _tech_loss(f"consecutive_forfeits:{actor}")
                    streak = consec_forfeits[actor]
                    print(f"  {actor}: forfeit ({result.get('reason')}) — streak {streak}")
                    continue
                consec_forfeits[actor] = 0
                sent_msg = result.pop("_msg", "")
                action = result.pop("_action", None)
                if sent_msg:
                    last_messages[actor] = sent_msg
                    print(f"  {actor} says: \"{sent_msg}\"")
                # If the server couldn't reach the opponent (NAT/network), the
                # orchestrator applies the action on the other server directly.
                if "comm_error" in result and action and not result.get("game_over"):
                    try:
                        await other.call_tool("receive_action", {
                            "game_id": game_id, "actor": actor,
                            "action": action, "message": sent_msg,
                        })
                        ha = await client.call_tool("get_hash", {"game_id": game_id})
                        hb = await other.call_tool("get_hash", {"game_id": game_id})
                        h1 = json.loads(ha.content[0].text if ha.content else "{}").get("hash")
                        h2 = json.loads(hb.content[0].text if hb.content else "{}").get("hash")
                        if h1 and h1 == h2:
                            result.pop("comm_error")
                            result["hash_match"] = True
                            print(f"  [sync] orchestrator recovered sync for {actor}")
                    except Exception as sync_err:
                        result["comm_error"] = str(sync_err)
                if result.get("hash_match") is False:
                    return _tech_loss("hash_mismatch")
                if "comm_error" in result:
                    return _tech_loss(f"comm_error:{result['comm_error']}")
                last_result = result
                if result.get("game_over"):
                    game_over = True
                    break
            board = _board_str(game_id)
            if board:
                print(board)
    return last_result


async def _game_loop(
    url_a: str, url_b: str, game_id: str, max_rounds: int,
) -> dict:
    """Drive alternating thief/cop turns until game_over or max_rounds (LLM mode).

    Returns:
        Final ActionResult dict, or a technical-loss sentinel on engine divergence.
    """
    from game.shared.gatekeeper import Gatekeeper
    from game.shared.tool_caller import ToolCaller

    model = os.environ.get("LLM_MODEL") or None
    caller = ToolCaller(Gatekeeper(model=model))
    auth = BearerAuth(_API_KEY)
    last_result: dict = {}
    async with Client(url_a + "/mcp", auth=auth, timeout=30.0) as ca, \
               Client(url_b + "/mcp", auth=auth, timeout=30.0) as cb:
        game_over, round_num = False, 0
        while not game_over and round_num < max_rounds:
            round_num += 1
            print(f"\n[round {round_num}]")
            for client, actor, system in [
                (ca, "thief", _SYSTEM_THIEF), (cb, "cop", _SYSTEM_COP),
            ]:
                result = await _agent_turn(caller, client, game_id, actor, system)
                if result.get("hash_match") is False:
                    return _tech_loss("hash_mismatch")
                if "comm_error" in result:
                    return _tech_loss(f"comm_error:{result['comm_error']}")
                last_result = result
                print(f"  {actor}: {result}")
                if result.get("game_over"):
                    game_over = True
                    break
    return last_result


def _sg_role(sg_n: int, game_type: str) -> str:
    """Return server_a's role for sub-game sg_n.

    Internal game: alternates thief/cop each sub-game (PRD §4).
    Bonus game: server_a=cop for sub-games 1-3, thief for 4-6 (PRD §12).
    """
    if game_type == "bonus":
        return "cop" if sg_n <= 3 else "thief"
    return "thief" if sg_n % 2 == 1 else "cop"


async def _run_series(
    url_a: str, url_b: str, mode: str, seed: int,
    max_rounds: int, game_type: str, grid: tuple[int, int],
    turn_timeout: float = 30.0, max_forfeits: int = 3,
    num_games: int = 6, view_radius: int = 1, max_moves: int = 25,
) -> list[dict]:
    """Run num_games valid sub-games, re-running on technical loss.

    Args:
        url_a: URL for server A.
        url_b: URL for server B.
        mode: "actor" or "llm".
        seed: Base seed; sub-game n uses seed + n - 1.
        max_rounds: Per-sub-game round cap (orchestrator loop ceiling).
        game_type: "internal" (alternating) or "bonus" (3+3 split, PRD §12).
        grid: Grid dimensions.
        turn_timeout: Seconds allowed per tool call (actor mode, §3.1).
        max_forfeits: Consecutive forfeit limit before technical loss.
        num_games: Number of valid sub-games to play (default 6).
        view_radius: Chebyshev distance within which opponent is visible.
        max_moves: Engine-level round cap passed to both game engines.

    Returns:
        List of sub-game result dicts for the report.
    """
    sub_games: list[dict] = []
    sg_n = 1
    while sg_n <= num_games:
        valid = False
        for attempt in range(1, _MAX_SG_RETRIES + 1):
            sg_seed = seed + sg_n - 1
            sg_id = f"match{seed:04d}_sg{sg_n:02d}" + (f"_r{attempt}" if attempt > 1 else "")
            cop_pos, thief_pos = _derive_positions(sg_seed, grid)

            a_role = _sg_role(sg_n, game_type)
            b_role = "cop" if a_role == "thief" else "thief"
            match_args = {"game_id": sg_id, "seed": sg_seed,
                          "cop_pos": cop_pos, "thief_pos": thief_pos,
                          "grid_size": list(grid), "view_radius": view_radius,
                          "max_moves": max_moves}
            auth = BearerAuth(_API_KEY)
            async with Client(url_b + "/mcp", auth=auth, timeout=30.0) as _cb:
                # Tell the opponent our URL so their take_action can call back to us.
                await _propose_match(_cb, {**match_args, "my_role": b_role,
                                           "initiator_url": url_a})
            async with Client(url_a + "/mcp", auth=auth, timeout=30.0) as _ca:
                await _propose_match(_ca, {**match_args, "my_role": a_role,
                                           "initiator_url": url_b})

            thief_url = url_a if a_role == "thief" else url_b
            cop_url = url_b if a_role == "thief" else url_a
            print(f"\n[sub-game {sg_n}/6  attempt {attempt}]  a={a_role} b={b_role}")

            result = (
                await _actor_game_loop(thief_url, cop_url, sg_id, max_rounds,
                                       turn_timeout, max_forfeits)
                if mode == "actor"
                else await _game_loop(thief_url, cop_url, sg_id, max_rounds)
            )

            if result.get("technical_loss"):
                reason = result.get("reason", "unknown")
                print(f"  TECHNICAL LOSS ({reason}) — {_MAX_SG_RETRIES - attempt} retries left")
                continue  # retry same sub-game number

            winner = result.get("winner")
            win_reason = result.get("win_reason") or "thief_survived"
            cop_pts, thief_pts = (20, 5) if winner == "cop" else (5, 10)
            terminal = _read_terminal(sg_id)
            sub_games.append({
                "sub_game": sg_n, "sg_id": sg_id, "initiator_role": a_role,
                "cop": "server_b" if a_role == "thief" else "server_a",
                "thief": "server_a" if a_role == "thief" else "server_b",
                "winner": winner, "win_reason": win_reason,
                "rounds": terminal.get("rounds"),
                "barriers_used": terminal.get("barriers_used"),
                "scores": {"cop": cop_pts, "thief": thief_pts},
            })
            print(f"  winner={winner} ({win_reason})")
            valid = True
            break

        if not valid:
            print(f"  Sub-game {sg_n} exhausted {_MAX_SG_RETRIES} retries — recording void.")
            sub_games.append({
                "sub_game": sg_n, "initiator_role": _sg_role(sg_n, game_type),
                "winner": None, "win_reason": "technical_loss",
                "scores": {"cop": 0, "thief": 0},
            })
        sg_n += 1
    return sub_games


def _build_results_summary(sub_games: list[dict]) -> str:
    """Build a compact per-sub-game results table for the email log.

    Args:
        sub_games: List of sub-game result dicts from _run_series.

    Returns:
        Formatted string with one line per sub-game showing winner, role, reason,
        rounds played, and scores.
    """
    lines = []
    for sg in sub_games:
        n = sg.get("sub_game", "?")
        a_role = sg.get("initiator_role", "?")
        b_role = "cop" if a_role == "thief" else "thief"
        winner = sg.get("winner") or "void"
        reason = sg.get("win_reason") or "technical_loss"
        rounds = sg.get("rounds") or "?"
        cop_pts = sg.get("scores", {}).get("cop", 0)
        thief_pts = sg.get("scores", {}).get("thief", 0)
        lines.append(
            f"  #{n:02}  winner={winner:<6}  ({reason:<16})  "
            f"A={a_role:<5} B={b_role:<5}  "
            f"rounds={rounds:<3}  cop={cop_pts}pts  thief={thief_pts}pts"
        )
    return "\n".join(lines)


async def _notify_both_servers(
    url_a: str, url_b: str, series_id: str,
    winner_name: str, cop_total: int, thief_total: int,
    num_sg: int, results_log: str = "",
) -> None:
    """Call send_game_summary on both servers so each sends its own result email.

    Args:
        url_a: Server A base URL.
        url_b: Server B base URL.
        series_id: Match series identifier.
        winner_name: Display name of the winning player.
        cop_total: Total cop score.
        thief_total: Total thief score.
        num_sg: Number of valid sub-games played.
        results_log: Per-sub-game results table to include in the email.
    """
    auth = BearerAuth(_API_KEY)
    payload = {
        "series_id": series_id, "winner_name": winner_name,
        "cop_total": cop_total, "thief_total": thief_total,
        "num_sub_games": num_sg, "results_log": results_log,
    }
    from fastmcp.exceptions import ToolError
    for url in (url_a, url_b):
        async with Client(url + "/mcp", auth=auth, timeout=30.0) as c:
            try:
                result = await c.call_tool("send_game_summary", payload)
                txt = result.content[0].text if result.content else "{}"
                print(f"[gmail] {url}: {txt}")
            except ToolError as exc:
                print(f"[gmail] {url}: skipped — {exc}")


def _maybe_send_report(sub_games: list[dict], series_id: str,
                       game_type: str = "internal") -> None:
    """Send the match report via Gmail if GMAIL_ENABLED=true and GMAIL_RECIPIENT is set."""
    from game.gmail.gmail_plugin import is_enabled
    if not is_enabled():
        print("[report] Gmail disabled — set GMAIL_ENABLED=true and GMAIL_RECIPIENT to enable.")
        return
    from game.gmail.reporter import build_report
    from game.gmail.sender import send_report
    report = build_report(sub_games, report_type=game_type)
    send_report(report)
    print(f"[report] Sent to {os.environ.get('GMAIL_RECIPIENT')}")


async def _async_main(seed: int, max_rounds: int, mode: str, actor_class: str,
                      models_dir: str, game_type: str, num_games: int = 6,
                      opponent_url: str = "", local_url: str = "",
                      port_a: int = 8001, port_b: int = 8002) -> None:
    """Start servers, run the sub-game series, print totals, send report."""
    cfg = _load_config()
    grid_cfg = cfg.get("grid_size", [5, 5])
    grid = (grid_cfg[0], grid_cfg[1])
    turn_timeout = float(cfg.get("turn_timeout_seconds", 30))
    max_forfeits = int(cfg.get("max_consecutive_forfeits", _MAX_FORFEIT_STREAK))
    num_games = num_games or int(cfg.get("num_games", 6))
    view_radius = int(cfg.get("view_radius", 1))
    max_moves = int(cfg.get("max_moves", 25))
    series_id = f"series{seed:04d}"
    print(f"[match] seed={seed} series_id={series_id} mode={mode} game_type={game_type}")

    # Resolve token/credentials paths relative to _REPO_ROOT so they work
    # regardless of the working directory the orchestrator is invoked from.
    for _env_key in ("GMAIL_TOKEN_PATH", "GMAIL_CREDENTIALS_PATH"):
        _val = os.environ.get(_env_key, "")
        if _val and not Path(_val).is_absolute():
            os.environ[_env_key] = str((_REPO_ROOT / _val).resolve())

    player_a = os.environ.get("PLAYER_NAME", "Player A")
    player_b = os.environ.get("OPPONENT_PLAYER_NAME", "Player B")

    # Normalise opponent URL: add http:// scheme if missing.
    if opponent_url and not opponent_url.startswith("http"):
        opponent_url = "http://" + opponent_url
    url_b = opponent_url or f"http://localhost:{port_b}"

    env_a = {**os.environ, "OPPONENT_MCP_URL": url_b,
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY,
             "PLAYER_NAME": player_a}
    env_b = {**os.environ, "OPPONENT_MCP_URL": f"http://localhost:{port_a}",
             "MCP_API_KEY": _API_KEY, "MCP_ALLOWED_API_KEYS": _API_KEY,
             "PLAYER_NAME": player_b}

    if mode == "actor":
        # Resolve models_dir to absolute so subprocess cwd doesn't matter.
        mdir = Path(models_dir) if Path(models_dir).is_absolute() else Path.cwd() / models_dir
        parent_src = str(_REPO_ROOT.parent / "src")
        existing_pypath = os.environ.get("PYTHONPATH", "")
        extra_pypath = parent_src + (os.pathsep + existing_pypath if existing_pypath else "")
        tables = {
            "COP_ACTOR_TABLE": str(mdir / "cop_qtable.npy"),
            "THIEF_ACTOR_TABLE": str(mdir / "thief_qtable.npy"),
        }
        env_a = {**env_a, "ACTOR_CLASS": actor_class, **tables, "PYTHONPATH": extra_pypath}
        env_b = {**env_b, "ACTOR_CLASS": actor_class, **tables, "PYTHONPATH": extra_pypath}

    # When local_url is given the caller owns server A — skip spawn and teardown.
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

        sub_games = await _run_series(url_a, url_b, mode, seed, max_rounds, game_type, grid,
                                       turn_timeout, max_forfeits, num_games, view_radius,
                                       max_moves)

        cop_total = sum(sg["scores"]["cop"] for sg in sub_games)
        thief_total = sum(sg["scores"]["thief"] for sg in sub_games)
        print(f"\n[series] totals: cop={cop_total}  thief={thief_total}")
        _maybe_send_report(sub_games, series_id, game_type)

        # Compute per-server totals to determine winner by name
        a_total, b_total = 0, 0
        for sg in sub_games:
            a_role = _sg_role(sg["sub_game"], game_type)
            b_role = "cop" if a_role == "thief" else "thief"
            a_total += sg["scores"].get(a_role, 0)
            b_total += sg["scores"].get(b_role, 0)
        winner_name = player_a if a_total >= b_total else player_b
        results = _build_results_summary(sub_games)
        await _notify_both_servers(
            url_a, url_b, series_id, winner_name,
            cop_total, thief_total, len(sub_games),
            results_log=results,
        )

    finally:
        if proc_a:
            proc_a.terminate()
            proc_a.wait()
        if proc_b:
            proc_b.terminate()
            proc_b.wait()
        print("[match] servers stopped")


def main() -> None:
    """Parse CLI args and run the async match orchestrator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=random.randint(0, 9999))
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument("--mode", choices=["llm", "actor"], default="llm",
                        help="llm: LLM tool-use loop; actor: Q-table actor")
    parser.add_argument("--actor-class", default="actor_t6.qtable_actor.QTableActor",
                        help="Dotted class path for ACTOR_CLASS (actor mode only)")
    parser.add_argument("--models-dir", default="models",
                        help="Directory containing cop_qtable.npy / thief_qtable.npy")
    parser.add_argument("--game-type", choices=["internal", "bonus"], default="internal",
                        help="internal: alternating roles; bonus: 3+3 split (PRD §12)")
    parser.add_argument("--num-games", type=int, default=0,
                        help="Sub-games to play (0 = use config.json value, default 6)")
    parser.add_argument("--opponent-url", default="",
                        help="External opponent MCP URL — skips starting server B locally")
    parser.add_argument("--local-url", default="",
                        help="URL of an already-running local server — skips starting server A")
    parser.add_argument("--port-a", type=int, default=8001,
                        help="Port for server A (default 8001)")
    parser.add_argument("--port-b", type=int, default=8002,
                        help="Port for server B (default 8002)")
    args = parser.parse_args()
    asyncio.run(_async_main(args.seed, args.max_rounds, args.mode,
                            args.actor_class, args.models_dir, args.game_type,
                            args.num_games, args.opponent_url, args.local_url,
                            args.port_a, args.port_b))


if __name__ == "__main__":
    main()
