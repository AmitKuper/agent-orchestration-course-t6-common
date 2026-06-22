"""CLI wrapper: python -m game <command>.

Exit codes:
    0 — success
    1 — illegal action (game continues)
    2 — game over
    3 — general error (bad args, missing game, etc.)
"""

from __future__ import annotations

import argparse
import json
import sys

from game.sdk.sdk import get_state, new_game, state_hash, submit_action


def _parse_pos(s: str) -> tuple[int, int]:
    """Parse 'col,row' into a tuple."""
    parts = s.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Position must be 'col,row', got {s!r}")
    return int(parts[0]), int(parts[1])


def _parse_grid(s: str) -> tuple[int, int]:
    """Parse 'cols,rows' into a tuple."""
    return _parse_pos(s)


def _out(data: object) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data))


def _err(msg: str, code: int = 3) -> None:
    """Print error message to stderr and exit."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def cmd_new(args: argparse.Namespace) -> None:
    """Handle 'game new' command."""
    try:
        result = new_game(args.grid, args.cop, args.thief)
        _out(result)
    except ValueError as exc:
        _err(str(exc))


def cmd_submit(args: argparse.Namespace) -> None:
    """Handle 'game submit' command."""
    try:
        result = submit_action(args.game_id, args.actor, args.action)
    except FileNotFoundError as exc:
        _err(str(exc))
        return

    _out(json.loads(result.to_json()))

    if result.game_over:
        sys.exit(2)
    if not result.success:
        sys.exit(1)


def cmd_get_state(args: argparse.Namespace) -> None:
    """Handle 'game get-state' command."""
    try:
        obs = get_state(args.game_id, args.actor)
        _out(json.loads(obs.to_json()))
    except (FileNotFoundError, ValueError) as exc:
        _err(str(exc))


def cmd_hash(args: argparse.Namespace) -> None:
    """Handle 'game hash' command."""
    try:
        h = state_hash(args.game_id)
        _out({"hash": h})
    except FileNotFoundError as exc:
        _err(str(exc))


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="game", description="Cop & Thief game CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a new game")
    p_new.add_argument("--grid", required=True, type=_parse_grid, metavar="COLS,ROWS")
    p_new.add_argument("--cop", required=True, type=_parse_pos, metavar="COL,ROW")
    p_new.add_argument("--thief", required=True, type=_parse_pos, metavar="COL,ROW")
    p_new.set_defaults(func=cmd_new)

    p_submit = sub.add_parser("submit", help="Submit an action")
    p_submit.add_argument("game_id")
    p_submit.add_argument("--actor", required=True, choices=["cop", "thief"])
    p_submit.add_argument("--action", required=True)
    p_submit.set_defaults(func=cmd_submit)

    p_state = sub.add_parser("get-state", help="Get observable state for an actor")
    p_state.add_argument("game_id")
    p_state.add_argument("--actor", required=True, choices=["cop", "thief"])
    p_state.set_defaults(func=cmd_get_state)

    p_hash = sub.add_parser("hash", help="Get state hash")
    p_hash.add_argument("game_id")
    p_hash.set_defaults(func=cmd_hash)

    return parser


def main() -> None:
    """Entry point for the game CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
