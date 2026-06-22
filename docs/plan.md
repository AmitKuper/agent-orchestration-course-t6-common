# Plan — Cop & Thief: Dual AI-Agent Pursuit over MCP

## Goal
Orchestrate two autonomous AI agents (Cop and Thief) that play a pursuit game on a 2D grid,
communicating via two independent MCP servers. The success metric is the **orchestration and
communication pipeline** — not the game-winning strategy.

---

## Overall Architecture

```
PLAYER A's side                              PLAYER B's side
─────────────────────────────────────────────────────────────────────

 LLM Orchestrator A                           LLM Orchestrator B
  (Actor + Agent)                              (Actor + Agent)
    │  calls local MCP tools                    │  calls local MCP tools
    ▼                                           ▼
┌─────────────────────┐   HTTP (MCP)   ┌─────────────────────┐
│   MCP Server A      │◄──────────────►│   MCP Server B      │
│   Game Engine A     │  propose_match │   Game Engine B     │
│   send_action       │  receive_action│   send_action       │
│   receive_action    │  validate_hash │   receive_action    │
│   submit_action     │                │   submit_action     │
│   get_state         │                │   get_state         │
│   game_hash         │                │   game_hash         │
│   Prompts           │                │   Prompts           │
│   Resources         │                │   Resources         │
└─────────────────────┘                └─────────────────────┘
         │                                        │
         └──────────── Game Engine ───────────────┘
              (replicated — each side runs its own
               authoritative copy, exchanges actions
               not state)
```

**Key distinction:**
- `Agent` (Part 2) = interpreter — parses LLM free text → action string; renders board state → text.
  Lives inside the LLM orchestrator, **not** inside the MCP server.
- `Actor` (Part 5) = strategy brain — decides what move to make. Team-specific.
- `MCP Server` (Part 3) = gateway — exposes game engine tools + inter-server communication tools.
  The LLM lives in the client, **not** in the server.

---

## Communication Protocol

### What is structured vs. natural language

| Communication | Format |
|---|---|
| Match setup (seed, mechanics, role assignment) | Structured JSON (MCP tool call) |
| Per-turn action (direction / BARRIER) | Structured (tool call param) |
| Per-turn message alongside the action | **Free natural language** ← the NL channel |
| State hash cross-validation | Structured |

The NL requirement (PRD §3): each turn an agent must send **one free-text message** alongside its
action. Agents exchange messages like *"Heading NE to cut off your escape route"* — not a rigid
protocol. This is the DecPOMDP communication channel; agents may bluff.

### Per-turn flow

```
1. Actor decides: move NE, message: "Closing in from the north"
2. Orchestrator calls local MCP: submit_action(game_id, "cop", "NE")
   → advances local Game engine
3. Local MCP server calls remote MCP: send_action(game_id, "cop", "NE", message="Closing in...")
   → remote engine applies the same action independently
4. Both sides call game_hash to cross-validate — mismatch = technical loss
5. Remote orchestrator polls receive_action / is notified → takes its turn
```

### Match setup handshake (structured, before any NL)

```
Initiator → Responder: propose_match(seed, mechanics, grid_size, roles)
Responder → Initiator: accept_match(agreed=True) | reject_match(reason)
Both: record agreed setup in game.log initial entry
```

---

## Shared Infrastructure

These cross-cutting pieces must exist before Parts 2–5 can be built.

### Gatekeeper (`src/game/shared/gatekeeper.py`)

All LLM API calls — from the Agent and the Actor — must go through the Gatekeeper.
**No agent or service calls the LLM directly.**

Responsibilities:
- Read rate limits from `config/rate_limits.json` (requests/min, tokens/min per model)
- Queue requests; enforce limits with a token-bucket or sliding window
- Retry with exponential backoff on 429 / transient errors
- Log every call: model, tokens in/out, latency, cost estimate → `docs/cost.md`

```python
class Gatekeeper:
    def call(self, messages, model, **kwargs) -> str:
        """Rate-limited, retried LLM call. Logs token usage."""
```

### Config files (mandatory deliverables)

```
config/
  config.yaml           # game defaults (already exists)
  rate_limits.json      # { "claude-opus-4-8": { "rpm": 50, "tpm": 100000 } }
  setup.json            # { "log_level": "INFO", "games_dir": "games" }

.env.example            # template for all env vars (committed; .env is git-ignored)
```

`.env.example` must document every env var the system uses:
```
MCP_API_KEY=
MCP_ALLOWED_API_KEYS=
OPPONENT_MCP_URL=
ANTHROPIC_API_KEY=
GMAIL_ENABLED=false
GMAIL_RECIPIENT=
GMAIL_TOKEN_PATH=config/gmail_token.json
GMAIL_CREDENTIALS_PATH=config/gmail_credentials.json
REPORT_TYPE=internal
```

---

## Project Parts

### Part 1 — Game Engine ✅ Complete

Pure Python state machine. No LLM, MCP, or CrewAI dependencies.

**Files:**
```
src/game/
  game.py          # public API: new, submit_action, get_state, state_hash, to_dict, from_dict
  game_rules.py    # GameRules mixin: move/barrier application, win detection
  game_state.py    # GameState dataclass
  actions.py       # MoveAction, BarrierAction, parse_action
  state.py         # ActionResult, ObservationState dataclasses
  constants.py     # directions, win reasons, actor names, compute_scores
  persistence.py   # state.json + JSONL game.log (PRD §4.1 format)
  sdk/sdk.py       # SDK entry point — all external callers go through here
  wrappers/
    cli.py         # CLI: game new / submit / get-state / hash
    crewai_tools.py
    mcp_tools.py   # FastMCP tool registrations (game engine tools only)
```

**Constraints:** 150-line max per file, all ≤ 150 lines. 84 tests, 97% coverage, 0 Ruff violations.

**Log format migration needed (Phase 8):**
The current `game.log` entries lack the `type` field and there is no `setup` entry.
The Logging section below describes the target format. Migration tasks:
- Add `"type": "turn"` to `append_log` entries
- Add `"type": "terminal"` to `append_terminal_log` entries
- Add `append_setup_log(game_id, seed, mechanics, base)` called by SDK on `new_game`
- Wire the NL `message` param through SDK → `append_log` (currently always `null`; filled by Agent in Part 2)

---

### Part 2 — Agent (NL Bridge) 🔲 To build

Translates between the LLM's free-text output and concrete game commands. Shared — no strategy logic.

**Responsibilities:**
- Render `ObservationState` → human-readable prompt text for the LLM
- Parse LLM free-text response → `(action: str, message: str)`
- Retry loop: re-prompt the LLM up to `max_illegal_retries` times on parse/illegal action failure
- Forfeit the turn after exhausting retries (stays in place, logs forfeit)
- Track consecutive forfeits → raise technical loss after `max_consecutive_forfeits`
- Pass the free-text `message` field to the log and to the inter-server send_action call

**Files to create:**
```
src/game/agent/
  __init__.py
  renderer.py     # ObservationState → prompt string (what does the LLM see?)
  parser.py       # LLM response string → (action, message) or ParseError
  agent.py        # retry loop: render → LLM call → parse → submit_action
```

**Renderer output example:**
```
Round 7 | You are the COP | Position: (2, 3)
Opponent last seen at: (4, 1) [within view]
Barriers placed: 2 / 5 remaining
Legal moves: N, NE, E, NW, BARRIER
Opponent's last message: "You'll never catch me in the open."
```

**Parser input/output:**
```
Input:  "I'll move northeast to intercept. Action: NE"
Output: action="NE", message="I'll move northeast to intercept."

Input:  "Moving diagonally right-up"   ← ambiguous
Output: ParseError("Cannot parse action from: 'Moving diagonally right-up'")
→ re-prompt with: "Invalid action. Legal moves are: N, NE, E, NW, BARRIER. Try again."
```

**Tests:**
```
tests/unit/test_renderer.py
tests/unit/test_parser.py
tests/integration/test_agent_retry.py   # retry loop, forfeit escalation
```

---

### Part 3 — MCP Server (hardening) 🔲 To build

Extends the existing `mcp_tools.py` with inter-server communication, prompts, resources, and auth.
The server is not tied to a fixed role — it plays cop or thief depending on the sub-game.

#### 3a — Inter-server communication tools

These tools make the two servers talk to each other (server-to-server HTTP):

```python
@mcp.tool()
def propose_match(opponent_url, seed, mechanics, grid_size, my_role) -> str:
    """Initiate match setup with the opponent server. Returns accept/reject."""

@mcp.tool()
def accept_match(proposal_id) -> str:
    """Accept an incoming match proposal. Initializes both engines with agreed params."""

@mcp.tool()
def send_action(game_id, actor, action, message) -> str:
    """Push this turn's action + NL message to the opponent's server."""
    # Calls opponent_url/receive_action over HTTP

@mcp.tool()
def receive_action(game_id, actor, action, message) -> str:
    """Inbound: apply opponent's action to local engine. Returns hash for validation."""

@mcp.tool()
def validate_state(game_id) -> str:
    """Cross-validate state hash with opponent. Returns match/mismatch."""
    # Calls opponent_url/game_hash, compares with local game_hash
```

The opponent server URL comes from env/config (`OPPONENT_MCP_URL`), never hard-coded.

#### 3b — MCP Prompts (LLM grounding)

Prompts are fetched by the orchestrator and injected as the system message before the LLM turn.
The server exposes role-specific prompts so the LLM knows the rules:

```python
@mcp.prompt()
def cop_rules(game_id: str) -> str:
    """System prompt grounding the LLM as the cop."""
    # Includes: win conditions, movement directions, barrier rule, turn order,
    # NL message requirement, current game_id

@mcp.prompt()
def thief_rules(game_id: str) -> str:
    """System prompt grounding the LLM as the thief."""
    # Same shared rulebook; role differences called out inline
```

Both prompts expose the **same rulebook** — role differences (barrier placement, etc.) are
constraints within it, not separate rule sets.

#### 3c — MCP Resources (live state the LLM can re-read)

Resources are URI-addressable documents the orchestrator (or LLM) can fetch at any time:

```python
@mcp.resource("game://config")
def rulebook() -> str:
    """Expose active config: grid_size, max_moves, max_barriers, observability."""

@mcp.resource("game://{game_id}/state/{actor}")
def game_state_resource(game_id: str, actor: str) -> str:
    """Live ObservationState for the given actor — re-readable each turn."""
```

#### 3d — API key authentication

Every inbound request (including server-to-server) must carry a valid API key:

```python
# middleware on mcp app
def auth_middleware(request):
    key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
    allowed = os.environ["MCP_ALLOWED_API_KEYS"].split(",")
    if key not in allowed:
        raise HTTPException(403, "Invalid API key")
```

Outbound calls present `MCP_API_KEY` from env. Never committed to source.

**Files to create/extend:**
```
src/game/wrappers/
  mcp_tools.py          # extend with inter-server tools
  mcp_prompts.py        # @mcp.prompt() definitions
  mcp_resources.py      # @mcp.resource() definitions
  mcp_auth.py           # auth middleware
  mcp_client.py         # HTTP client for calling opponent server
```

**Tests:**
```
tests/unit/test_mcp_prompts.py
tests/unit/test_mcp_resources.py
tests/integration/test_mcp_auth.py
tests/integration/test_inter_server.py   # two servers, local URLs, full handshake
```

---

## Logging

Two separate log files are written per match (under `games/<game_id>/`):

### 1. `game.log` — debug log (human + machine readable)

Verbose JSONL written after every event. Designed to be easy to read and trace.
Every line has a `ts` timestamp, `game_id`, and an event `type`.

**Entry types:**

```jsonl
{"ts":"...", "game_id":"abc123", "type":"setup",   "seed":42, "grid":[5,5], "cop":[0,0], "thief":[4,4], "mechanics":{...}}
{"ts":"...", "game_id":"abc123", "type":"turn",    "turn":1, "actor":"thief", "action":"move", "from":[4,4], "to":[3,3], "barrier_at":null, "message":"Moving SW to avoid you.", "success":true, "error":null, "state_after":{"cop":[0,0],"thief":[3,3],"barriers":[]}}
{"ts":"...", "game_id":"abc123", "type":"turn",    "turn":2, "actor":"cop",   "action":"barrier", "from":[0,0], "to":[0,0], "barrier_at":[0,0], "message":"Blocking your retreat.", "success":true, "error":null, "state_after":{"cop":[0,0],"thief":[3,3],"barriers":[[0,0]]}}
{"ts":"...", "game_id":"abc123", "type":"forfeit", "turn":5, "actor":"cop",   "reason":"parse_error", "consecutive_forfeits":1}
{"ts":"...", "game_id":"abc123", "type":"terminal","winner":"cop", "win_reason":"capture", "rounds":14, "barriers_used":3, "scores":{"cop":20,"thief":5}}
```

Replay guarantee: applying every `turn` entry's `action` from the `setup` state
deterministically reproduces the `terminal` state.

### 2. `report.json` — mail-ready report

Written once at match end by `reporter.py`. Contains **exactly** the JSON that will be
emailed — nothing more, nothing less. Safe to inspect before enabling the Gmail plugin.

**Internal game shape:**
```json
{
  "group_name": "Team-Alpha",
  "students": [{"name": "...", "id": "..."}],
  "github_repo": "https://github.com/team-alpha/marl-cop-thief",
  "cop_mcp_url": "https://cop-mcp-alpha.prefect.run",
  "thief_mcp_url": "https://thief-mcp-alpha.prefect.run",
  "timezone": "Asia/Jerusalem",
  "played_at": "2026-06-22T14:30:00+03:00",
  "sub_games": [
    {"sub_game":1, "initiator_role":"thief", "cop":"player_b", "thief":"player_a",
     "winner":"cop", "win_reason":"capture", "moves":14, "barriers_used":3,
     "scores":{"cop":20,"thief":5}}
  ],
  "totals": {"cop": 90, "thief": 40}
}
```

**Bonus game shape:** same `sub_games` array but with `report_type:"bonus_game"`,
both groups' names, 4 MCP URLs, 2 GitHub repos, `totals_by_group`, `bonus_claim`,
and `mutual_agreement: true` — see PRD §10 for full schema.

**Why two files?** `game.log` is the authoritative replay record and is always written.
`report.json` is derived from it and written only at match end. The Gmail plugin reads
`report.json` directly — no re-parsing of `game.log` required.

---

### Part 4 — Gmail Reporting 🔲 To build

**Plugin is OFF by default.** It activates only when both conditions are true:
- `GMAIL_ENABLED=true` is set in the environment
- `GMAIL_RECIPIENT` is set to a non-empty address in the environment

If either is missing/unset the plugin is silently skipped — no error, no email.
This makes the internal game safe to run without any mail config, and lets the bonus
game opt in by simply setting those two env vars.

After all 6 valid sub-games, the **initiating server** emails the JSON report once.

```
src/game/gmail/
  reporter.py     # build_report(sub_games, report_type) → dict (PRD §10 schema)
  sender.py       # send_report(report_dict) — reads GMAIL_RECIPIENT from env
  gmail_plugin.py # is_enabled() check; called by orchestrator before sending
```

**Report shape:** see PRD §10. Derived from `report.json` (see Logging section above).

**Auth:** Gmail API with token-based OAuth2 (token stored in env/config, not password).
**Dedup:** sender checks a sent-flag in state before emailing; re-runs for technical losses do not
re-trigger the email.

**Config keys (all in `.env`, never committed):**
```
GMAIL_ENABLED=false          # must be explicitly set to "true" to activate
GMAIL_RECIPIENT=             # destination address — blank = plugin disabled
GMAIL_TOKEN_PATH=config/gmail_token.json
GMAIL_CREDENTIALS_PATH=config/gmail_credentials.json
REPORT_TYPE=internal         # "internal" | "bonus"
```

**Tests:**
```
tests/unit/test_reporter.py        # build_report output matches PRD §10 schema exactly
tests/unit/test_gmail_plugin.py    # is_enabled() off by default, on when both vars set
tests/integration/test_sender.py   # send_report with mock Gmail API (no real email sent)
```

---

### Part 5 — Actor 🔲 To build

The strategy brain. The Agent calls `ActorWrapper.get_action(obs)` — it does not know or care
what backend is behind the wrapper.

#### Flow

```
Agent
  │  obs: ObservationState
  ▼
ActorWrapper.get_action(obs) → (action, nl_message)
  │  calls backend, then generates NL message from template
  ▼
BaseActor.get_action(obs) → action string
  │
  ├── RandomActorBackend   random.choice(obs.legal_moves)   ← default, build now
  └── RLActorBackend       stub — interface only             ← internals from another repo
```

#### Interface (the contract backends must satisfy)

```python
class BaseActor(ABC):
    @abstractmethod
    def get_action(self, obs: ObservationState) -> str:
        """Return one action string given current observation."""

    def on_result(self, obs: ObservationState, action: str, result: ActionResult) -> None:
        """Called after the action resolves. No-op for random; used by learning backends."""
```

```python
class ActorWrapper:
    def get_action(self, obs: ObservationState) -> tuple[str, str]:
        """Return (action, nl_message). The Agent calls this every turn."""
        action = self.backend.get_action(obs)
        message = self._render_message(obs, action)  # simple template, no LLM needed
        return action, message

    def on_result(self, obs, action, result):
        self.backend.on_result(obs, action, result)
```

The NL message is a simple template generated by `ActorWrapper` — e.g. `"Moving NE."` /
`"Placing barrier."`. Satisfies the protocol requirement without a LLM call.

#### Backends

**RandomActorBackend** — default, built now:
```python
class RandomActorBackend(BaseActor):
    def get_action(self, obs: ObservationState) -> str:
        return random.choice(obs.legal_moves)
    # on_result is a no-op
```

**RLActorBackend** — stub only; `get_action` and `on_result` raise `NotImplementedError`.
Internals (state encoding, policy, persistence) come from a separate repo and are not
planned here. Dropping in the real implementation requires only filling those two methods.

#### Files

```
src/actor/
  base_actor.py       # BaseActor ABC: get_action(), on_result() (default no-op)
  actor_wrapper.py    # ActorWrapper: calls backend, generates NL message template
  random_actor.py     # RandomActorBackend: random.choice(obs.legal_moves)
  rl_actor.py         # RLActorBackend: stub — raises NotImplementedError
```

#### Tests

```
tests/unit/test_actor_wrapper.py   # wrapper calls backend, returns (action, message)
tests/unit/test_random_actor.py    # always returns a legal move; no repeats aren't guaranteed
```

---

## Folder Structure (full target)

```
src/
  game/
    game.py / game_rules.py / game_state.py
    actions.py / state.py / constants.py / persistence.py
    sdk/sdk.py
    shared/
      gatekeeper.py
    agent/
      renderer.py / parser.py / agent.py
    wrappers/
      cli.py / crewai_tools.py
      mcp_tools.py / mcp_prompts.py / mcp_resources.py
      mcp_auth.py / mcp_client.py
    gmail/
      reporter.py / sender.py / gmail_plugin.py
  actor/
    base_actor.py / actor_wrapper.py / random_actor.py / rl_actor.py

tests/
  unit/
    test_game.py / test_actions.py / test_state.py / test_persistence.py
    test_renderer.py / test_parser.py
    test_mcp_prompts.py / test_mcp_resources.py
  integration/
    test_full_game.py / test_sdk_wrapper.py
    test_cli_wrapper.py / test_crewai_wrapper.py / test_mcp_wrapper.py
    test_agent_retry.py / test_inter_server.py / test_mcp_auth.py

config/
  config.yaml           # game defaults
  rate_limits.json      # LLM API rate limits (Gatekeeper)
  setup.json            # log level, paths

docs/
  PRD.md / plan.md / TODO.md / cost.md
  PRD_game.md / PRD_agent.md / PRD_mcp.md / PRD_gmail.md
```

---

## Implementation Order (remaining work)

| # | Part | Deliverable | Dependency |
|---|---|---|---|
| 0 | Infra | Gatekeeper, config files, .env.example | — |
| 0b | Part 1 cleanup | Log format migration (type field, setup entry, message wiring) | — |
| 1 | Part 2 | Agent: renderer + parser + retry loop | Game ✅, Gatekeeper |
| 2 | Part 3a | MCP inter-server tools + mcp_client | Game ✅, Agent |
| 3 | Part 3b/c | MCP prompts + resources | Agent (renderer) |
| 4 | Part 3d | API key auth middleware | Part 3a |
| 5 | Part 4 | Gmail reporter + sender (plugin off) | Game ✅ |
| 6 | Part 5 | Actor (heuristic / LLM strategy) | Agent, MCP, Gatekeeper |
| 7 | Phase 8 | Partial observation, match orchestration | All above |

---

## Out of Scope (Phase 8 — deferred)

- Partial observation / `view_radius` filtering in `get_state`
- `state_hash` cross-engine validation on every turn
- Scoring accumulation across 6 sub-games
- Full match orchestration loop (6 sub-games, role alternation, technical loss re-run)
