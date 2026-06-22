# Plan — Game Engine (Part 1)

## Goal
Implement a pure Python `Game` class that is the single authoritative state machine for the Cop & Thief game. No LLM, MCP, or CrewAI dependencies. Wrap it in three access layers once the core is stable.

---

## Folder Structure

```
src/
  game/
    __init__.py
    game.py             # Game class — core state machine
    actions.py          # MoveAction, BarrierAction, action parsing
    state.py            # ObservationState, ActionResult dataclasses
    constants.py        # directions, win reasons, actor names, defaults
    persistence.py      # state.json read/write, game.log JSONL
    sdk/
      sdk.py            # SDK entry point — all external callers go through here
    wrappers/
      cli.py            # CLI wrapper
      crewai_tools.py   # CrewAI @tool wrappers
      mcp_tools.py      # FastMCP tool registrations

games/                  # runtime game instance directories (git-ignored)
  <game_id>/
    state.json
    game.log

tests/
  unit/
    test_game.py
    test_actions.py
    test_state.py
    test_persistence.py
  integration/
    test_full_game.py

config/
  config.yaml           # grid_size, max_moves, max_barriers, etc.

pyproject.toml
```

---

## Core Design Principle

```
Game (pure Python)
    ├── CLI wrapper        → testing, debugging, manual play
    ├── CrewAI @tool       → local agent development
    └── FastMCP tools      → production MCP server (required by PRD)
```

The core is written once. The wrappers are thin — they translate their respective calling conventions into `Game` method calls and serialize the result to JSON.

---

## Game Class API

### Construction
```python
game = Game.new(grid_size, cop_pos, thief_pos, mechanics)
```
- `grid_size`: `(int, int)` — e.g. `(5, 5)`
- `cop_pos`: `(int, int)` — `(col, row)`, 0-indexed, top-left origin
- `thief_pos`: `(int, int)`
- `mechanics`: dict of active game settings (from config, agreed at match setup)
- Returns: `Game` instance
- Raises: `ValueError` if positions are off-grid, identical, or on a barrier

### Methods

```python
game.submit_action(actor, action) → ActionResult
game.get_state(actor)             → ObservationState
game.state_hash()                 → str
```

---

## Data Contracts (JSON-serializable dataclasses)

### `ActionResult`
```python
@dataclass
class ActionResult:
    success: bool
    error: str | None       # reason if illegal — used to re-prompt the agent
    game_over: bool
    winner: str | None      # "cop" | "thief"
    win_reason: str | None  # "capture" | "thief_trapped" | "thief_survived" | "cop_trapped"
```

### `ObservationState`
```python
@dataclass
class ObservationState:
    actor: str                          # "cop" | "thief"
    round: int
    my_pos: tuple[int, int]
    opponent_pos: tuple[int, int] | None  # null when outside view_radius (deferred — always visible for now)
    barriers: list[tuple[int, int]]
    legal_moves: list[str]              # pre-computed: ["N", "NE", "E", ...] or includes "BARRIER"
    barriers_remaining: int | None      # cop only; None for thief
```

> **Partial observation deferred.** `opponent_pos` is always returned for now. Visibility filtering (Chebyshev distance ≤ `view_radius`) will be added to `get_state()` in a later phase. The engine will own that logic — it must never leak into the wrapper layers.

---

## Actions

| Action | Who | Description |
|--------|-----|-------------|
| `N` `NE` `E` `SE` `S` `SW` `W` `NW` | Both | Move one step in that direction |
| `BARRIER` | Cop only | Place barrier on current cell; cop does not move this turn |

Validation in `submit_action`:
- Move target must be within grid bounds
- Move target must not be a barrier cell
- `BARRIER`: actor must be cop, `barriers_remaining > 0`, current cell not already a barrier
- Illegal action → `ActionResult(success=False, error="<reason>", ...)`

---

## Persistence

Each game instance is persisted under `games/<game_id>/`:

```
games/
  <game_id>/
    state.json     # full canonical state (both positions, barriers, round, mechanics)
    game.log       # append-only JSONL — one entry per turn (PRD §4.1 format)
```

`state.json` is rewritten after every `submit_action`. The wrappers load it on every call, call the method, and save it back. The `Game` object itself is stateless between CLI/MCP calls — all state lives on disk.

---

## Agent & Opponent Tracking

Agents do **not** receive the opponent's position from the engine when out of view. They track the opponent by reasoning over the **natural language message history** — each agent must say what it did ("I moved north", "I placed a barrier"). This is why the free-text channel is mandatory each turn (PRD §3).

- Honest agents can always reconstruct exact opponent position from the message log.
- Bluffing is a valid strategy — if an agent lies, the opponent's belief drifts.
- The engine enforces ground truth; it does not enforce honest messaging.

---

## Wrappers

### 1. CLI
Entry point: `python -m game <command>`

```bash
game new --grid 5,5 --cop 0,0 --thief 4,4          # → {"game_id": "abc123"}
game submit <game_id> --actor cop --action NE        # → ActionResult JSON
game get-state <game_id> --actor cop                 # → ObservationState JSON
game hash <game_id>                                  # → {"hash": "a3f9c2d1"}
```

All output is JSON to stdout. Errors go to stderr with a non-zero exit code.

### 2. CrewAI Tools
Each method becomes a `@tool`. The game instance is loaded from disk by `game_id`.

```python
@tool("submit_action")
def submit_action(game_id: str, actor: str, action: str) -> str:
    """Submit a move or barrier placement. Returns ActionResult as JSON."""

@tool("get_state")
def get_state(game_id: str, actor: str) -> str:
    """Get the current observable game state for the given actor. Returns ObservationState as JSON."""
```

### 3. FastMCP Tools
Same shape as CrewAI tools, registered with FastMCP. The MCP server calls these on behalf of the agent after each LLM turn. Required for the inter-group bonus game.

---

## Implementation Order

1. `Game` core — state, move validation, win detection, barrier logic
2. `ActionResult` + `ObservationState` dataclasses with `.to_json()`
3. Persistence (`state.json` + JSONL log)
4. Full test suite (unit + integration) — target ≥ 85% coverage
5. CLI wrapper
6. CrewAI wrapper
7. FastMCP wrapper

---

## Out of Scope (this phase)

- Partial observation / view radius filtering
- `state_hash` cross-engine validation
- Match setup handshake (seed, mechanics negotiation)
- Scoring accumulation across sub-games
- Gmail reporting
