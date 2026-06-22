# TODO

## Game Engine

### Phase 1 — Core State Machine
> Pure Python `Game` class, no external dependencies.

- [ ] Define `Game.new(grid_size, cop_pos, thief_pos, mechanics)` — validate positions, initialize state
- [ ] Implement 8-direction move validation (bounds check, barrier check)
- [ ] Implement `BARRIER` action (cop only, max 5, no stacking)
- [ ] Implement win condition detection after every action:
  - [ ] Capture (same cell)
  - [ ] Thief trapped (no legal moves on thief's turn)
  - [ ] Cop trapped (no legal move + no barrier available on cop's turn)
  - [ ] Thief survived (round `max_moves` completed)
- [ ] Implement `submit_action(actor, action)` → `ActionResult`
- [ ] Implement `get_state(actor)` → `ObservationState` (full visibility for now)
- [ ] Pre-compute `legal_moves` list in `ObservationState`
- [ ] Implement `state_hash()` → `str`

### Phase 2 — Data Contracts
> Serializable dataclasses for all inputs/outputs.

- [ ] `ActionResult` dataclass with `.to_json()`
- [ ] `ObservationState` dataclass with `.to_json()`
- [ ] `MoveAction` / `BarrierAction` typed input objects
- [ ] `constants.py` — directions, win reasons, actor names

### Phase 3 — Persistence
> Game instance directory under `games/<game_id>/`.

- [ ] Generate `game_id` on `Game.new()`
- [ ] Write `state.json` on every `submit_action`
- [ ] Append JSONL entry to `game.log` on every `submit_action` (PRD §4.1 format)
- [ ] `Game.load(game_id)` — restore instance from `state.json`
- [ ] Write terminal log entry on game over (winner, win_reason, scores, rounds)

### Phase 4 — Test Suite
> Target ≥ 85% coverage. Zero Ruff violations.

- [ ] Unit tests for move validation (all 8 directions, off-grid, into barrier)
- [ ] Unit tests for `BARRIER` action (cop only, limit, stacking)
- [ ] Unit tests for each win condition
- [ ] Unit tests for `get_state` filtering (barriers_remaining None for thief)
- [ ] Unit tests for `state_hash` determinism
- [ ] Integration tests — full sub-game replay from log
- [ ] Integration tests — illegal move retry flow

### Phase 5 — CLI Wrapper
> `python -m game <command>` — JSON to stdout, errors to stderr.

- [ ] `game new` command
- [ ] `game submit` command
- [ ] `game get-state` command
- [ ] `game hash` command
- [ ] Exit codes (0 = ok, 1 = illegal action, 2 = game over, 3 = error)

### Phase 6 — CrewAI Wrapper
> `@tool` decorators for local agent development.

- [ ] `submit_action` tool
- [ ] `get_state` tool
- [ ] `new_game` tool
- [ ] Tool descriptions written for LLM consumption

### Phase 7 — FastMCP Wrapper
> FastMCP tools for production MCP server.

- [ ] Register `new_game`, `submit_action`, `get_state` as MCP tools
- [ ] MCP prompts — role grounding (cop vs. thief rules, turn order)
- [ ] MCP resources — live config + current game state
- [ ] API key authentication (`MCP_ALLOWED_API_KEYS`, `MCP_API_KEY`)

### Phase 8 — Deferred (later phases)
> Not in scope for the current implementation.

- [ ] Partial observation — `view_radius` filtering in `get_state`
- [ ] `state_hash` cross-engine validation via mutual-position-validation tool
- [ ] Match setup handshake (seed, mechanics negotiation between two servers)
- [ ] Scoring accumulation across 6 sub-games
- [ ] Gmail reporting
