# TODO

## Game Engine

### Phase 1 — Core State Machine ✅ Complete
> Pure Python `Game` class, no external dependencies.

- [x] Define `Game.new(grid_size, cop_pos, thief_pos, mechanics)` — validate positions, initialize state
- [x] Implement 8-direction move validation (bounds check, barrier check)
- [x] Implement `BARRIER` action (cop only, max 5, no stacking)
- [x] Implement win condition detection after every action:
  - [x] Capture (same cell)
  - [x] Thief trapped (no legal moves on thief's turn)
  - [x] Cop trapped (no legal move + no barrier available on cop's turn)
  - [x] Thief survived (round `max_moves` completed)
- [x] Implement `submit_action(actor, action)` → `ActionResult`
- [x] Implement `get_state(actor)` → `ObservationState` (full visibility for now)
- [x] Pre-compute `legal_moves` list in `ObservationState`
- [x] Implement `state_hash()` → `str`

### Phase 2 — Data Contracts ✅ Complete
> Serializable dataclasses for all inputs/outputs.

- [x] `ActionResult` dataclass with `.to_json()`
- [x] `ObservationState` dataclass with `.to_json()`
- [x] `MoveAction` / `BarrierAction` typed input objects
- [x] `constants.py` — directions, win reasons, actor names

### Phase 3 — Persistence ✅ Complete
> Game instance directory under `games/<game_id>/`.

- [x] Generate `game_id` on `Game.new()`
- [x] Write `state.json` on every `submit_action`
- [x] Append JSONL entry to `game.log` on every `submit_action` (PRD §4.1 format)
- [x] `Game.load(game_id)` — restore instance from `state.json`
- [ ] Write terminal log entry on game over (winner, win_reason, scores, rounds)

### Phase 4 — Test Suite ✅ Complete
> Target ≥ 85% coverage. Zero Ruff violations.

- [x] Unit tests for move validation (all 8 directions, off-grid, into barrier)
- [x] Unit tests for `BARRIER` action (cop only, limit, stacking)
- [x] Unit tests for each win condition
- [x] Unit tests for `get_state` filtering (barriers_remaining None for thief)
- [x] Unit tests for `state_hash` determinism
- [x] Integration tests — full sub-game replay from log
- [x] Integration tests — illegal move retry flow
> Coverage: 97% | Tests: 45 passed | Ruff: 0 violations

### Phase 5 — CLI Wrapper ✅ Complete
> `python -m game <command>` — JSON to stdout, errors to stderr.

- [x] `game new` command
- [x] `game submit` command
- [x] `game get-state` command
- [x] `game hash` command
- [x] Exit codes (0 = ok, 1 = illegal action, 2 = game over, 3 = error)

### Phase 6 — CrewAI Wrapper ✅ Complete
> `@tool` decorators for local agent development.

- [x] `submit_action` tool
- [x] `get_state` tool
- [x] `new_game` tool
- [x] Tool descriptions written for LLM consumption

### Phase 7 — FastMCP Wrapper ✅ Complete
> FastMCP tools for production MCP server.

- [x] Register `new_game`, `submit_action`, `get_state`, `game_hash` as MCP tools
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
- [ ] Terminal log entry on game over (winner, win_reason, scores, rounds)
- [ ] MCP prompts (role grounding) and resources (live state)
- [ ] MCP API key authentication
