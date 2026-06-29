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
import random
import sys

# Force UTF-8 output so emoji/non-ASCII in opponent messages don't crash on
# Windows consoles that default to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from match_helpers.orchestrator import _async_main


def main() -> None:
    """Parse CLI args and run the async match orchestrator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=random.randint(0, 9999))
    parser.add_argument("--max-rounds", type=int, default=None,
                        help="Rounds per sub-game (overrides config max_moves). "
                             "Thief surviving this many rounds wins. Default: config value.")
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
    parser.add_argument("--time-debug", action="store_true",
                        help="Print per-phase timing (qtable/llm/take_action) for every turn")
    args = parser.parse_args()
    asyncio.run(_async_main(
        args.seed, args.max_rounds, args.mode,
        args.actor_class, args.models_dir, args.game_type,
        args.num_games, args.opponent_url, args.local_url,
        args.port_a, args.port_b, args.time_debug,
    ))


if __name__ == "__main__":
    main()
