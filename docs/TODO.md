# TODO

## Game Engine — Part 1

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

### Phase 3 — Persistence ✅ Complete (commit 9fad400)
> Game instance directory under `games/<game_id>/`.

- [x] Generate `game_id` on `Game.new()`
- [x] Write `state.json` on every `submit_action`
- [x] Append JSONL entry to `game.log` on every `submit_action` (PRD §4.1 format)
- [x] `Game.load(game_id)` — restore instance from `state.json`
- [x] Write terminal log entry on game over (winner, win_reason, scores, rounds)

### Phase 4 — Test Suite ✅ Complete
> Target ≥ 85% coverage. Zero Ruff violations.

- [x] Unit tests for move validation (all 8 directions, off-grid, into barrier)
- [x] Unit tests for `BARRIER` action (cop only, limit, stacking)
- [x] Unit tests for each win condition
- [x] Unit tests for `get_state` filtering (barriers_remaining None for thief)
- [x] Unit tests for `state_hash` determinism
- [x] Integration tests — full sub-game replay from log
- [x] Integration tests — illegal move retry flow
> Coverage: 97% | Tests: 84 passed | Ruff: 0 violations

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
> FastMCP game-engine tools (Part 3 inter-server tools are in Phase 10).

- [x] Register `new_game`, `submit_action`, `get_state`, `game_hash` as MCP tools

### Phase 8 — Log Format Migration 🔲 To do
> Align `game.log` with the target format described in `docs/plan.md` (Logging section).

- [ ] Add `"type": "turn"` field to `append_log` entries in `persistence.py`
- [ ] Add `"type": "terminal"` field to `append_terminal_log` entries
- [ ] Add `append_setup_log(game_id, seed, mechanics, base)` — called by SDK on `new_game`
- [ ] Add optional `message: str | None` param to SDK `submit_action` (wired through to log; always `None` until Part 2 fills it)
- [ ] Update all affected tests

---

## Shared Infrastructure — Phase 9 🔲 To do
> Cross-cutting pieces required before Parts 2–5.

- [ ] Create `src/game/shared/gatekeeper.py` — rate-limited, retried LLM call wrapper
  - [ ] Read limits from `config/rate_limits.json`
  - [ ] Token-bucket or sliding-window rate limiting
  - [ ] Exponential backoff on 429 / transient errors
  - [ ] Log every call (model, tokens in/out, latency) → `docs/cost.md`
- [ ] Create `config/rate_limits.json`
- [ ] Create `config/setup.json`
- [ ] Create `.env.example` documenting all env vars
- [ ] Unit tests: `tests/unit/test_gatekeeper.py`

---

## Part 2 — Agent (NL Bridge) — Phase 10 🔲 To do
> Renderer + parser + retry loop. No strategy logic.

- [ ] `src/game/agent/renderer.py` — `ObservationState` → human-readable prompt text
  - [ ] Include: round, role, position, opponent last seen, barriers, legal moves, opponent's last message
- [ ] `src/game/agent/parser.py` — LLM free-text → `(action: str, message: str)` or `ParseError`
  - [ ] Match action keyword from legal moves list
  - [ ] Extract everything before the action keyword as the NL message
- [ ] `src/game/agent/agent.py` — retry loop
  - [ ] Render state → call Gatekeeper (LLM) → parse → submit_action
  - [ ] Re-prompt up to `max_illegal_retries` on `ParseError` or illegal action
  - [ ] After exhausting retries: forfeit turn (stay in place), write `forfeit` log entry
  - [ ] Track consecutive forfeits → raise `TechnicalLoss` after `max_consecutive_forfeits`
- [ ] `tests/unit/test_renderer.py`
- [ ] `tests/unit/test_parser.py`
- [ ] `tests/integration/test_agent_retry.py` — retry loop, forfeit escalation, technical loss

---

## Part 3 — MCP Server Hardening

### Phase 11a — Inter-server Communication Tools 🔲 To do
> Server-to-server HTTP — the two MCP servers talk to each other.

- [ ] `src/game/wrappers/mcp_client.py` — HTTP client for calling opponent MCP server
  - [ ] Read `OPPONENT_MCP_URL` from env
  - [ ] Send `MCP_API_KEY` on all outbound requests
- [ ] Add to `mcp_tools.py`:
  - [ ] `propose_match(seed, mechanics, grid_size, my_role)` — initiate match handshake
  - [ ] `accept_match(proposal_id)` — inbound: accept and initialize both engines
  - [ ] `send_action(game_id, actor, action, message)` — push turn to opponent
  - [ ] `receive_action(game_id, actor, action, message)` — inbound: apply to local engine
  - [ ] `validate_state(game_id)` — cross-check game_hash with opponent
- [ ] `tests/integration/test_inter_server.py` — two local servers, full handshake + game turn

### Phase 11b — MCP Prompts & Resources 🔲 To do
> LLM grounding via standard MCP surfaces.

- [ ] `src/game/wrappers/mcp_prompts.py`
  - [ ] `cop_rules(game_id)` — system prompt: win conditions, movement, barrier, turn order, NL message requirement
  - [ ] `thief_rules(game_id)` — same rulebook, role differences called out
- [ ] `src/game/wrappers/mcp_resources.py`
  - [ ] `game://config` — active config (grid_size, max_moves, max_barriers, observability)
  - [ ] `game://{game_id}/state/{actor}` — live `ObservationState`
- [ ] `tests/unit/test_mcp_prompts.py`
- [ ] `tests/unit/test_mcp_resources.py`

### Phase 11c — API Key Authentication 🔲 To do
> Every inbound request must carry a valid key from `MCP_ALLOWED_API_KEYS`.

- [ ] `src/game/wrappers/mcp_auth.py` — middleware checking `X-API-Key` / `Authorization` header
- [ ] Reject with 403 if key not in allowed set
- [ ] `tests/integration/test_mcp_auth.py` — valid key passes, missing/wrong key rejected

---

## Part 4 — Gmail Reporting — Phase 12 🔲 To do
> Plugin OFF by default. Activates only when `GMAIL_ENABLED=true` AND `GMAIL_RECIPIENT` are set.

- [ ] `src/game/gmail/reporter.py` — `build_report(sub_games, report_type)` → dict (PRD §10 schema)
  - [ ] Internal game shape (group_name, students, URLs, sub_games, totals)
  - [ ] Bonus game shape (both groups, 4 URLs, totals_by_group, bonus_claim, mutual_agreement)
  - [ ] Write `report.json` to `games/<match_id>/report.json`
- [ ] `src/game/gmail/sender.py` — `send_report(report_dict)` via Gmail API
  - [ ] Token-based OAuth2 (no username/password)
  - [ ] Email body = only the JSON, no free text
  - [ ] Dedup: check sent-flag before sending; re-runs for technical losses do not re-send
- [ ] `src/game/gmail/gmail_plugin.py` — `is_enabled()` guard
- [ ] `tests/unit/test_reporter.py` — output matches PRD §10 schema
- [ ] `tests/unit/test_gmail_plugin.py` — off by default, on when both vars set
- [ ] `tests/integration/test_sender.py` — mock Gmail API, no real email sent

---

## Part 5 — Actor — Phase 13 🔲 To do
> ActorWrapper + RandomActorBackend (default) + RLActorBackend stub (interface only).
> The Agent calls ActorWrapper.get_action(obs) → (action, message). It never calls a backend directly.

- [ ] `src/actor/base_actor.py` — `BaseActor` ABC: `get_action(obs) → str`, `on_result(obs, action, result)` (default no-op)
- [ ] `src/actor/actor_wrapper.py` — `ActorWrapper`: calls `backend.get_action()`, generates NL message from template, exposes `on_result()` passthrough
- [ ] `src/actor/random_actor.py` — `RandomActorBackend`: `random.choice(obs.legal_moves)`; `on_result` is no-op
- [ ] `src/actor/rl_actor.py` — `RLActorBackend` stub: `get_action` and `on_result` raise `NotImplementedError`; internals come from a separate repo
- [ ] Wire `ActorWrapper` into `Agent` — Agent calls `wrapper.get_action(obs)` and `wrapper.on_result(obs, action, result)` after each turn
- [ ] `tests/unit/test_actor_wrapper.py` — wrapper returns `(action, message)` tuple; delegates to backend; message is non-empty string
- [ ] `tests/unit/test_random_actor.py` — always returns a value from `obs.legal_moves`; no errors on any legal observation

---

## Phase 14 — Deferred / Phase 8 🔲 To do (after Parts 2–5)
> Needed for full production run; deferred until the pipeline is proven end-to-end.

- [ ] Partial observation — `view_radius` (Chebyshev) filtering in `get_state`
  - [ ] Opponent position hidden when outside `view_radius`
  - [ ] Barriers outside radius hidden
  - [ ] Hidden state must never leak into Actor
- [ ] `state_hash` cross-engine validation after every turn (via `validate_state` tool)
- [ ] Scoring accumulation across 6 sub-games (match-level state, not sub-game-level)
- [ ] Full match orchestration loop:
  - [ ] 6 sub-games, role alternation each sub-game
  - [ ] Technical loss detection → void sub-game, re-run
  - [ ] `max_consecutive_forfeits` → technical loss
  - [ ] Shared `random_seed` for start positions
- [ ] Deploy both MCP servers to cloud (e.g. Prefect) with public URLs
- [ ] Bonus inter-group game support (3+3 role split, PRD §12)
