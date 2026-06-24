# Cop & Thief — Shared Infrastructure (hw6-common)

Parts 1–4 of the HW6 Cop & Thief project. Two AI agents play a pursuit game on a 5×5 grid, communicating via MCP servers.

---

## Architecture

```
run_match.py (orchestrator)
    |
    |── MCP HTTP ──> Server A (port 8001)      Server B (port 8002)
                         |                          |
                    Game engine               Game engine
                    Actor backend             Actor backend
                    LLM (message)             LLM (message)
```

Each server runs its own authoritative game engine. They exchange **actions** (never state), then cross-validate with a state hash after every turn. The orchestrator drives turn alternation.

**Actor injection is required.** The server has no built-in strategy — each team must supply a `BaseActor` subclass. See [Implementing an Actor](#implementing-an-actor) below.

---

## Setup

```bash
git clone --recurse-submodules <repo>
cd hw6-common
uv sync
```

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Minimum `.env` for local Ollama:

```
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=devstral:latest
MCP_API_KEY=my-secret-key
MCP_ALLOWED_API_KEYS=my-secret-key
```

For Anthropic instead:

```
ANTHROPIC_API_KEY=sk-ant-...
MCP_API_KEY=my-secret-key
MCP_ALLOWED_API_KEYS=my-secret-key
```

---

## Implementing an Actor

Every team must implement `BaseActor` from `actor.base_actor`:

```python
from actor.base_actor import BaseActor
from game.state import ActionResult, ObservationState

class MyActor(BaseActor):
    def get_action(self, obs: ObservationState) -> str:
        """Return one legal action from obs.legal_moves."""
        ...

    def on_result(self, obs: ObservationState, action: str, result: ActionResult) -> None:
        """Optional: receive feedback after each action (for learning agents)."""
        ...
```

### `ObservationState` fields

| Field | Type | Description |
|-------|------|-------------|
| `actor` | `str` | `"cop"` or `"thief"` |
| `round` | `int` | Current round number |
| `my_pos` | `tuple[int, int]` | Your position `(col, row)` |
| `opponent_pos` | `tuple[int, int] \| None` | Opponent position (None if out of view radius) |
| `barriers` | `list[tuple[int, int]]` | Active barrier positions |
| `legal_moves` | `list[str]` | Valid actions this turn — **always return one of these** |
| `barriers_remaining` | `int \| None` | Barriers the cop can still place (None for thief) |

### Legal actions

Directions: `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`  
Cop only: `BARRIER` (places a wall on current cell, max 5 per game)

### Saving and loading weights (optional)

If your actor is trainable, implement `save` and a `load` classmethod:

```python
def save(self, path) -> None:
    np.save(str(path), self._weights)

@classmethod
def load(cls, role: str, path, **kwargs) -> "MyActor":
    actor = cls(role=role, **kwargs)
    actor._weights = np.load(str(path))
    actor.epsilon = 0.0   # pure exploitation after training
    return actor
```

---

## Wiring Your Actor into the Server

The server selects an actor via **environment variables** — no code changes needed.

### Required env vars

| Variable | Description |
|----------|-------------|
| `ACTOR_CLASS` | Dotted import path to your `BaseActor` subclass |
| `ACTOR_TABLE` | *(optional)* Path to saved weights file — triggers `.load(role, path)` |

### Priority order in `_create_actor_wrapper`

1. `ACTOR_CLASS` set → import class, optionally load weights, wrap with `LLMMessageWrapper` (LLM generates the NL message)
2. No `ACTOR_CLASS` → `LLMActorWrapper` (LLM decides both action and message)
3. No LLM configured → **error** — an LLM is always required for NL messages

### Example: inject a trained Q-table actor

```
ACTOR_CLASS=actor_t6.qtable_actor.QTableActor
ACTOR_TABLE=models/cop_qtable.npy
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=devstral:latest
```

The server will call `QTableActor.load(role="cop", path="models/cop_qtable.npy")` and wrap it so the Q-table picks every action while Ollama generates the NL message.

---

## Running a Match

### With trained actor + Ollama messages (recommended)

```bash
# from hw6-common/
uv run python scripts/run_match.py --mode actor \
    --actor-class mypackage.mymodule.MyActor \
    --models-dir path/to/models \
    --seed 42
```

`run_match.py` automatically:
- Starts both MCP servers as subprocesses
- Injects `ACTOR_CLASS`, `ACTOR_TABLE`, and `PYTHONPATH` into each server
- Server A plays **thief** → loads `thief_qtable.npy`
- Server B plays **cop** → loads `cop_qtable.npy`
- Drives turn alternation until game over or `--max-rounds`

### Pure LLM mode (LLM decides action and message)

```bash
uv run python scripts/run_match.py --mode llm --seed 42
```

### CLI options

```
--seed INT          Random seed for start positions (default: random)
--max-rounds INT    Max rounds before game ends (default: 30)
--mode {llm,actor}  llm: LLM tool-use loop; actor: actor backend via take_turn
--actor-class STR   Dotted class path (actor mode only, default: actor_t6.qtable_actor.QTableActor)
--models-dir STR    Directory with cop_qtable.npy / thief_qtable.npy (default: models)
```

---

## Replaying a Game

```bash
# from the repo root (parent of hw6-common)
uv run python replay.py hw6-common/games/server_a/<game_id>/game.log

# auto-picks the most recent game
uv run python replay.py
```

Press **Enter** to step through each turn. Press **q** to quit.

Each turn shows:
- Which actor moved and where
- The NL message generated by the LLM
- The board state after the move (C=cop, T=thief, X=capture, B=barrier)

---

## Project Structure

```
hw6-common/
├── src/
│   ├── actor/
│   │   ├── base_actor.py          # BaseActor ABC — implement this
│   │   ├── actor_wrapper.py       # Bridges Agent ↔ backend
│   │   ├── llm_actor.py           # LLM decides action + message
│   │   ├── llm_message_wrapper.py # Custom backend action + LLM message
│   │   └── random_actor.py        # Random baseline (for training opponents)
│   └── game/
│       ├── game.py                # Core state machine
│       ├── state.py               # ObservationState, ActionResult dataclasses
│       ├── sdk/sdk.py             # SDK entry point
│       └── wrappers/
│           ├── mcp_server.py      # FastMCP server entry point
│           ├── mcp_routes.py      # Inter-server REST routes
│           └── mcp_agent_tools.py # get_state / take_action MCP tools
├── scripts/
│   └── run_match.py               # Match orchestrator
├── config/
│   ├── rate_limits.json           # LLM rate limiting config
│   └── setup.json                 # App config
├── .env.example                   # Env var template
└── tests/
```

---

## Running Tests

```bash
uv run ruff check .                          # zero violations required
.venv/Scripts/python.exe -m pytest tests/    # Windows
.venv/bin/python -m pytest tests/            # Linux/macOS
```
