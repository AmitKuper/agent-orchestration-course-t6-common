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

### Phase 8 — Log Format Migration ✅ Complete (commit 89f2b25)
> Align `game.log` with the target format described in `docs/plan.md` (Logging section).

- [x] Add `"type": "turn"` field to `append_log` entries in `persistence.py`
- [x] Add `"type": "terminal"` field to `append_terminal_log` entries
- [x] Add `append_setup_log(game_id, seed, mechanics, grid_size, cop_pos, thief_pos, base)` — called by SDK on `new_game`
- [x] Add optional `message: str | None` param to SDK `submit_action` (wired through to log)
- [x] Update all affected tests

---

## Shared Infrastructure — Phase 9 ✅ Complete (commit ce77955)
> Cross-cutting pieces required before Parts 2–5.

- [x] Create `src/game/shared/gatekeeper.py` — rate-limited, retried LLM call wrapper
  - [x] Read limits from `config/rate_limits.json`
  - [x] Token-bucket / sliding-window rate limiting
  - [x] Exponential backoff on 429 / transient errors
  - [x] Log every call (model, tokens in/out, latency) → `docs/cost.md`
- [x] Create `config/rate_limits.json`
- [x] Create `config/setup.json`
- [x] Create `.env.example` documenting all env vars
- [x] Unit tests: `tests/unit/test_gatekeeper.py`

---

## Part 2 — Agent (NL Bridge) — Phase 10 ✅ Complete (commit 47dcc1c)
> Renderer + parser + retry loop. No strategy logic.

- [x] `src/game/agent/renderer.py` — `ObservationState` → human-readable prompt text
  - [x] Include: round, role, position, opponent last seen, barriers, legal moves, opponent's last message
- [x] `src/game/agent/parser.py` — LLM free-text → `(action: str, message: str)` or `ParseError`
  - [x] Match action keyword from legal moves list
  - [x] Extract everything before the action keyword as the NL message
- [x] `src/game/agent/agent.py` — retry loop
  - [x] Render state → call Gatekeeper (LLM) → parse → submit_action
  - [x] Re-prompt up to `max_illegal_retries` on `ParseError` or illegal action
  - [x] After exhausting retries: forfeit turn (stay in place), write `forfeit` log entry
  - [x] Track consecutive forfeits → raise `TechnicalLoss` after `max_consecutive_forfeits`
- [x] `tests/unit/test_renderer.py`
- [x] `tests/unit/test_parser.py`
- [x] `tests/unit/test_agent.py` (retry loop, forfeit escalation, technical loss)

---

## Part 3 — MCP Server Hardening

### Phase 11a — Inter-server Communication Tools ✅ Complete (commit 2d97a5c)
> Server-to-server HTTP — the two MCP servers talk to each other.

- [x] `src/game/wrappers/mcp_client.py` — HTTP client for calling opponent MCP server
  - [x] Read `OPPONENT_MCP_URL` from env
  - [x] Send `MCP_API_KEY` on all outbound requests
- [x] `mcp_routes.py` — custom REST routes registered on FastMCP instance:
  - [x] `POST /game/propose_match` — accept match proposal, create local game
  - [x] `POST /game/receive_action` — inbound: apply opponent's action to local engine
  - [x] `POST /game/hash` — return local state hash for cross-validation
- [x] `mcp_server.py` — `new_game_tool` + `take_turn` MCP tools; `_patch_state_game_id` fix
- [x] `scripts/run_match.py` — async orchestrator using FastMCP `Client` with `BearerAuth`
> Two-server match ran end-to-end: 28 rounds, cop captured thief, `hash_match: True` every turn (commit 24d222c)

### Phase 11b.5 — LLM-Backed Actor ✅ Complete
> Wire an actual LLM into the game flow. Backend selected by env vars; fallback to random actor.

- [x] `src/game/shared/gatekeeper.py` — add Ollama backend alongside Anthropic
  - [x] `ANTHROPIC_API_KEY` set → Anthropic; otherwise → Ollama (`OLLAMA_BASE_URL`, default localhost)
  - [x] `_call_anthropic()` / `_call_ollama()` split into private methods
  - [x] `_default_model()` helper returns correct model per backend
- [x] `src/actor/llm_actor.py` — new module
  - [x] `LLMActorBackend(BaseActor)` — renders obs → calls Gatekeeper → parses response; stores NL message
  - [x] `LLMActorWrapper(ActorWrapper)` — overrides `_render_message` to use LLM message not template
  - [x] `create_llm_wrapper(role)` — factory reading `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` / `LLM_MODEL`
- [x] `src/game/wrappers/mcp_server.py` — `_create_actor_wrapper(role)` factory; uses LLM when env configured
- [x] `tests/unit/test_llm_actor.py` — 12 tests covering backend, wrapper, factory, fallback
- [x] `tests/unit/test_gatekeeper.py` — added Ollama tests (backend selection, call, system prompt)

### Phase 11b — MCP Prompts & Resources ✅ Complete
> LLM grounding via standard MCP surfaces.

- [x] `src/game/wrappers/mcp_prompts.py`
  - [x] `cop_rules(game_id)` — system prompt: win conditions, movement, barrier, turn order, NL message requirement
  - [x] `thief_rules(game_id)` — same rulebook, role differences called out
- [x] `src/game/wrappers/mcp_resources.py`
  - [x] `game://config` — active config (grid_size, max_moves, max_barriers, observability)
  - [x] `game://{game_id}/state/{actor}` — live `ObservationState`
- [x] `tests/unit/test_mcp_prompts.py`
- [x] `tests/unit/test_mcp_resources.py`

### Phase 11d — LLM Tool-Use Orchestrator ✅ Complete
> LLM lives in the orchestrator (`run_match.py`), not inside the server. Matches PRD architecture.

- [x] `src/game/shared/mcp_tool_format.py`
  - [x] `ToolCall` / `LLMResponse` dataclasses
  - [x] `to_anthropic_tools()` / `to_ollama_tools()` — unified → wire format conversion
  - [x] `parse_anthropic_response()` / `parse_ollama_response()`
  - [x] `anthropic_tool_result_messages()` / `ollama_tool_result_messages()`
- [x] `src/game/shared/tool_caller.py` — `ToolCaller` class
  - [x] `call_with_tools(messages, tools, tool_executor, system)` — async tool-use loop
  - [x] Internal `_raw_call()` using Gatekeeper's rate-limit; `_call_anthropic()` / `_call_ollama()`
- [x] `src/game/wrappers/mcp_agent_tools.py`
  - [x] `GAME_TOOLS` list — tool defs for `get_state` and `take_action`
  - [x] `register_agent_tools(mcp)` — registers `get_state` + `take_action` MCP tools
- [x] `src/game/wrappers/mcp_server.py` — `register_agent_tools`, `register_prompts`, `register_resources` added
- [x] `scripts/run_match.py` — rewritten: `ToolCaller` drives LLM that calls `get_state` then `take_action`
- [x] `tests/unit/test_mcp_tool_format.py` — 11 tests
- [x] `tests/unit/test_tool_caller.py` — 5 tests
- [x] `tests/unit/test_mcp_agent_tools.py` — 7 tests
> Tests: 185 passed | Ruff: 0 violations
> End-to-end game run (seed=77): cop captured thief in 2 rounds, hash_match=True all turns (llama3.1:8b vs llama3.1:8b)

### Phase 11c — API Key Authentication ✅ Complete (commit 2d97a5c)
> Every inbound request must carry a valid key from `MCP_ALLOWED_API_KEYS`.

- [x] `src/game/wrappers/mcp_state.py` — `auth_ok(request)` checks `Authorization: Bearer` / `X-API-Key` header
- [x] All routes in `mcp_routes.py` call `auth_ok`; reject with 403 if key not in allowed set
- [x] `scripts/run_match.py` uses `BearerAuth` on all MCP tool calls

---

## Part 4 — Gmail Reporting — Phase 12 ✅ Complete (commit 5c5c75c)
> Plugin OFF by default. Activates only when `GMAIL_ENABLED=true` AND `GMAIL_RECIPIENT` are set.

- [x] `src/game/gmail/reporter.py` — `build_report(sub_games, report_type)` → dict (PRD §10 schema)
  - [x] Internal game shape (group_name, students, URLs, sub_games, totals)
  - [x] Bonus game shape (both groups, 4 URLs, totals_by_group, bonus_claim, mutual_agreement)
  - [x] Write `report.json` to `games/<match_id>/report.json`
- [x] `src/game/gmail/sender.py` — `send_report(report_dict)` via Gmail API
  - [x] Token-based OAuth2 (no username/password)
  - [x] Email body = only the JSON, no free text
  - [x] Dedup: check sent-flag before sending; re-runs for technical losses do not re-send
- [x] `src/game/gmail/gmail_plugin.py` — `is_enabled()` guard
- [x] `tests/unit/test_reporter.py` — output matches PRD §10 schema
- [x] `tests/unit/test_gmail_plugin.py` — off by default, on when both vars set

---

## Part 5 — Actor — Phase 13 ✅ Complete (commit 8dbee63)
> ActorWrapper + RandomActorBackend (default) + RLActorBackend stub (interface only).
> The Agent calls ActorWrapper.get_action(obs) → (action, message). It never calls a backend directly.

- [x] `src/actor/base_actor.py` — `BaseActor` ABC: `get_action(obs) → str`, `on_result(obs, action, result)` (default no-op)
- [x] `src/actor/actor_wrapper.py` — `ActorWrapper`: calls `backend.get_action()`, generates NL message from template, exposes `on_result()` passthrough
- [x] `src/actor/random_actor.py` — `RandomActorBackend`: `random.choice(obs.legal_moves)`; `on_result` is no-op
- [x] `src/actor/rl_actor.py` — `RLActorBackend` stub: `get_action` and `on_result` raise `NotImplementedError`
- [x] `ActorWrapper` wired into `take_turn` MCP tool in `mcp_server.py`
- [x] `tests/unit/test_actor.py` — wrapper returns `(action, message)` tuple; delegates to backend

---

## Phase 14 — Production Hardening 🚧 In Progress (MCP architecture complete)

- [x] `state_hash` cross-engine validation after every turn — `hash_match` in `take_action`
- [x] Shared `random_seed` for start positions — agreed at match setup via `propose_match`
- [x] **PRD §6 compliance — LLM lives in orchestrator, not server:**
  - [x] `src/game/wrappers/actor_loader.py` — pure Q-table backend loader (no LLM)
  - [x] `mcp_agent_tools.py` — `get_actor_action` tool: returns Q-table action without LLM
  - [x] `mcp_server.py` — removed `take_turn` + `_create_actor_wrapper` (were calling LLM inside server)
  - [x] `scripts/run_match.py` — `_actor_game_loop` rewritten: get_actor_action → LLM here → take_action
- [x] **Full 6-sub-game series with role alternation (PRD §4):**
  - [x] `run_match.py` runs 6 sub-games per series, alternating server_a/server_b roles
  - [x] Seed increments per sub-game (sg_seed = seed + sg_n - 1)
  - [x] Scores accumulated; totals printed after series
- [x] Gmail reporting wired in `run_match.py` — `_maybe_send_report` called after 6 sub-games
- [x] **Technical loss detection → void sub-game, re-run (§3.1):**
  - [x] `_actor_turn()` helper with `asyncio.wait_for(turn_timeout)` per tool call
  - [x] Forfeit on timeout, actor error, or `success=False`
  - [x] `max_consecutive_forfeits` → technical loss; sub-game re-runs up to `_MAX_SG_RETRIES`
- [x] **§4.1/§10 Terminal log data in reports:**
  - [x] `_read_terminal(sg_id)` reads `game.log` for `rounds` + `barriers_used`
  - [x] Both fields added to sub-game result dict
- [x] **§5 Config reading from file:**
  - [x] `config/config.json` created with all game parameters
  - [x] `mcp_resources.py` loads `_GAME_CONFIG` from file (fallback to defaults)
  - [x] `run_match.py` reads `grid_size`, `turn_timeout_seconds`, `max_consecutive_forfeits` from config
  - [x] `setup.json` updated to reference `config/config.json`
- [x] **Bonus 3+3 role split (PRD §12):** `_sg_role()` returns cop/cop/cop/thief/thief/thief for bonus mode
- [x] **Full MCP protocol for ALL inter-server calls (Phase 14b):**
  - [x] `mcp_sync_tools.py` — `receive_action`, `get_hash`, `propose_match_tool` as real MCP tools (replaced REST routes)
  - [x] `mcp_agent_tools.py` — `take_action` now `async def`; uses FastMCP `Client` to call opponent's MCP tools
  - [x] `mcp_routes.py` — gutted to `/health` only (all game sync via MCP now)
  - [x] `run_match.py` — `propose_match` calls via FastMCP `Client`; removed `_post()` REST helper
  - [x] `mcp_client.py` — deleted (was REST-only; superseded by FastMCP `Client` calls)
  - [x] `tests/unit/test_mcp_sync_tools.py` — 7 tests for new sync tools
  - [x] `tests/unit/test_mcp_agent_tools.py` — updated async `take_action` test
  - [x] 203 tests pass, 0 Ruff violations
  - [x] End-to-end 2-game match verified (all `/mcp` calls, `hash_match: True`)
- [ ] Partial observation — `view_radius` (Chebyshev) filtering in `get_state`
  - [ ] Opponent position hidden when outside `view_radius`
  - [ ] Barriers outside radius hidden
  - [ ] Hidden state must never leak into Actor
- [ ] Deploy both MCP servers to cloud (e.g. Prefect) with public URLs
- [ ] Bonus inter-group game (requires cloud deployment)
