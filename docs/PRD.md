# PRD — Cop & Thief: Dual AI-Agent Pursuit over MCP

> Product Requirements Document for HW6 ("Orchestration of AI Agents").
> This document is the authoritative project spec; it mirrors the assignment and records the team's
> implementation decisions.

## 1. Overview & Goal
Orchestrate two autonomous AI agents — the **Cop** and the **Thief** — that play a dynamic pursuit
game on a 2D grid. The agents run as separate processes and communicate in **free natural language**
over **two independent MCP servers** (one per agent).

The success metric is the **orchestration and communication pipeline** — two agents that coordinate a
full game autonomously, end to end, with no manual intervention — **not** the game-winning strategy.
Each agent must parse the other's natural-language messages, infer the opponent's
position under partial observation, and translate that into physical moves on the grid.

## 2. Project parts (build breakdown)
Each part is **self-contained and independently tested**, with a **full test suite**.

| # | Part | Responsibility | Ownership |
| :-: | :--- | :--- | :--- |
| 1 | Game | Rules, grid state machine, move validation, capture/barrier detection, scoring | **Shared** |
| 2 | Agent | **Parser/translator:** turns free natural-language messages into concrete game commands (move / barrier) and renders game state back into text | **Shared** |
| 3 | MCP server(s) | Expose tools (send/receive messages, mutual position validation) via FastMCP | **Shared** |
| 4 | Gmail | Send the JSON game report by email | **Shared** |
| 5 | Actor | **Strategy/decision-making:** decides the next action (heuristic / distance / Q-table / prompt). The strategic "brain." | **Team-specific** |

**Agent vs. Actor.** The **Agent** is the interpreter — it parses the opponent's free text into game
commands and turns board state into outgoing text — and is shared. The **Actor** is the strategy that
chooses *what* to do; it is the only team-specific part, so each team's Cop and Thief embody that
team's own play style while sharing the same parsing, game, MCP, and reporting infrastructure.

**Team layout:** two teams of 2 people each. Parts 1–4 (Game, Agent, MCP, Gmail) are shared between
the teams; part 5 (Actor) is implemented per team.

## 3. Game rules
**Selectable mechanics.** Several rules below are **modular, optional mechanics** rather than fixed
constants — most notably **observability** (partial vs. full), but also things like grid size,
`max_moves`, and `max_barriers`. The **agent (its MCP server) decides which mechanics are in effect**
for a game: the **initiating** server **proposes** the active set when it requests a match, and the
responder must **explicitly accept** it before play starts (a unilaterally-announced set is not
enough — both sides must agree, especially in the bonus game so neither side gets a one-sided
advantage). The agreed set is recorded in each side's log (§4.1). The config file (§5) supplies only
the **defaults** the initiator proposes from.

- **Grid:** 2D, default **5×5**, sized via the config file (generic architecture — **no hard-coding**).
- **Starting positions:** at the start of **every sub-game** the cop and the thief are placed on
  **random, distinct cells**. Because each side runs its own engine (§6.2), the positions are derived
  from a **shared random seed agreed during match setup**, so both engines independently generate the
  **same** start state. Re-rolling positions outside this agreed seed is not allowed.
- **Turns:** turn-based; the **thief moves first**, then the cop — together one **round**. The game is
  a state machine — each round changes the board state.
- **Mandatory message + action each turn.** On its turn an agent must (a) send **one free-text
  message** *and* (b) submit **exactly one action** (a move, or — for the cop — a barrier placement).
  A silent turn (action with no message) is a protocol violation handled like an illegal move below;
  the orchestration goal requires the natural-language exchange.
- **Movement:** **8 directions** including diagonals (up/down/left/right + 4 diagonals); exactly one
  step per turn. A move **off-grid or into a barrier cell is illegal** (see *Illegal/unparseable
  actions* below) — it is not silently clamped.
- **Observability** (a selectable mechanic — see above): **partial observation is ON by default**,
  but the parties may agree to turn it off for a given game.
  - When **on** (`partial_observation: true`): each agent's engine exposes to that agent **only what
    it is allowed to see** — its own position, barriers within `view_radius`, and the opponent **only
    when within `view_radius`**. The opponent's exact position is **never** present in the data an
    agent receives out of view; it can only be **inferred from the opponent's text** (the DecPOMDP
    framing). Implementations must enforce this — the hidden state must not leak into the Actor.
  - When **off**: both agents see the full grid and game state (simpler interim / sanity-check mode).
- **Barrier:** instead of moving, the cop may place a **barrier on his own current cell**.
  - This consumes the cop's action for that round (he does not move that turn) and **counts as his
    turn** toward the round limit.
  - The barrier cell becomes **impassable for both players** (like a wall or grid edge). The cop
    remains on that cell for the rest of the turn but, since it is now a barrier, **once he leaves it
    he cannot re-enter it**. Barriers do not stack (one per cell).
  - The cop may place at most **5 barriers** per sub-game (`max_barriers`); the thief cannot place
    barriers.
- **Win conditions:**
  - **Capture (cop wins):** the cop and the thief occupy the **same cell** — whether the cop moves
    onto the thief or the thief moves onto the cop. Because barrier cells are impassable to the thief,
    capture can only occur on a non-barrier cell.
  - **Thief trapped (cop wins):** if it is the **thief's** turn and he has **no legal move** (boxed in
    by barriers and/or grid edges), the cop wins that sub-game immediately.
  - **Cop trapped (thief wins):** mirror rule — if it is the **cop's** turn and he has **no legal
    action** (no legal move *and* no barrier he may place, e.g. walled in with barriers exhausted),
    the thief wins that sub-game immediately.
  - **Thief survives (thief wins):** the thief is not captured by the end of round `max_moves` (25).
    The capture check is evaluated **after each action**; if round 25 completes with no capture, the
    thief wins.

### 3.1 Illegal/unparseable actions & timeouts
- **Illegal or unparseable action → re-prompt, then forfeit.** If a submitted action is illegal
  (off-grid, into a barrier, a 6th barrier, thief placing a barrier, missing message) or cannot be
  parsed into a valid command, the engine **rejects it with a reason** and re-prompts. The acting
  agent gets up to **`max_illegal_retries`** attempts (default **2**). If it still fails, the turn is
  **forfeited** (the agent stays in place) and play continues.
- **Per-turn timeout.** Each turn must complete within **`turn_timeout_seconds`** (default **30**). A
  turn that exceeds the limit is treated as a forfeited turn.
- **Escalation to technical loss.** Repeated protocol failure — exhausting retries/timeouts for
  **`max_consecutive_forfeits`** turns in a row (default **3**), an unreachable opponent, or engine
  **state divergence** (§6.2) — voids the sub-game as a **technical loss** (§10): it is discarded and
  re-run, it carries **no score**, and the reason is logged.

## 4. Match structure & scoring
- **Sub-game:** one chase, capped at **25 rounds** (`max_moves`). A **round** = the thief's turn
  followed by the cop's turn; each player therefore acts up to 25 times.
- **Game:** a series of **6 sub-games** run consecutively; scores accumulate and are reported
  together at the end.
- **Role alternation.** The two MCP servers represent **players**, not fixed roles; roles swap every
  sub-game. The **initiating** server (the one that requests a match from the other) starts as the
  **thief** in sub-game 1, becomes the **cop** in sub-game 2, and continues alternating through all 6
  sub-games — so each player serves as thief 3 times and cop 3 times. The other server plays the
  opposite role each sub-game.

| Sub-game | 1 | 2 | 3 | 4 | 5 | 6 |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: |
| **Initiator** | Thief | Cop | Thief | Cop | Thief | Cop |
| **Responder** | Cop | Thief | Cop | Thief | Cop | Thief |

| Result | Cop points | Thief points |
| :--- | :-: | :-: |
| Cop wins (capture **or** thief trapped) | 20 | 5 |
| Thief wins (survives **or** cop trapped) | 5 | 10 |

Both cop-win reasons (`capture`, `thief_trapped`) score **20/5**; both thief-win reasons
(`thief_survived`, cop-trapped) score **5/10**. A **technical loss** (§3.1, §10) is void — it carries
**no score** and is re-run. Max possible team score in a full inter-group game is 90; minimum is 30.

### 4.1 Game log & replay
The engine **must record a complete, machine-readable log** for every sub-game that is sufficient to
**fully reconstruct the play** turn by turn — independently of any GUI. Requirements:
- One log per sub-game (e.g. append-only **JSON Lines**), capturing initial setup and every turn.
- The **initial state**: grid size, the **agreed mechanics set** and **random seed** (§3, §6.2),
  observability mode, role assignment, and both start positions.
- For **each turn**, an entry recording: round index, actor (`cop`/`thief`), action
  (`move` | `barrier`), `from`/`to` cells, the barrier cell (if any), the free-text **message** the
  agent sent that turn, and the **resulting board state** (both positions + all barriers).
- A **terminal** entry: winner, win reason, total rounds, barriers used, final scores.
- Replaying the logged actions from the initial state must deterministically reproduce the final
  state (the log is the source of truth for the report and for debugging/visualization).

**Coordinate convention.** Cells are `[x, y]`, **0-indexed**, origin at the **top-left**: `x` =
column (increasing rightward), `y` = row (increasing downward). Both engines must use this convention
so independently-generated logs and replays agree.

**Per-turn log entry (one JSONL line):**
```json
{
  "turn": 7,
  "actor": "thief",
  "action": "move",
  "from": [2, 3],
  "to": [3, 4],
  "barrier_at": null,
  "message": "Heading for the open corner to shake you off.",
  "state_after": { "cop": [1, 1], "thief": [3, 4], "barriers": [[0, 0], [4, 4]] }
}
```
For a barrier action: `"action": "barrier"`, `"barrier_at": [x, y]`, with `from`/`to` equal (the cop
forfeits the move).

## 5. Configuration file
**Hard-coding game parameters is forbidden.** All parameters live in a central `config.json` /
`config.yaml`, including at least the following. These are **defaults**: the initiating MCP server
may override the selectable mechanics (e.g. observability) per game and announce them via MCP (§3, §6).

| Parameter | Description | Default |
| :--- | :--- | :-: |
| `grid_size` | 2D grid dimensions | `[5, 5]` |
| `max_moves` | Max **rounds** per sub-game (thief+cop = one round) | `25` |
| `num_games` | Sub-games per series | `6` |
| `max_barriers` | Max barriers the cop may place | `5` |
| `scoring.cop_win` | Cop points on capture | `20` |
| `scoring.thief_win` | Thief points on escape | `10` |
| `scoring.cop_loss` | Cop points when thief escapes | `5` |
| `scoring.thief_loss` | Thief points when caught | `5` |
| `partial_observation` | Enable limited view radius | `true` |
| `view_radius` | View radius in cells, **Chebyshev distance** (a square window; matches 8-direction movement) | `2` |
| `random_seed` | Seed for start-position RNG; shared/agreed per match so both engines match | (agreed) |
| `turn_timeout_seconds` | Max wall-clock per turn before forfeit (§3.1) | `30` |
| `max_illegal_retries` | Re-prompt attempts before a turn is forfeited (§3.1) | `2` |
| `max_consecutive_forfeits` | Forfeited turns in a row before technical loss (§3.1) | `3` |

**Operational/connection settings** (opponent MCP URL, host/port, log directory) and **secrets**
(API keys, §6.1) likewise must **not** be hard-coded — keep them in config/env. Per-match values that
two parties must share (e.g. `random_seed`, the agreed mechanics set) are fixed during match setup,
not silently defaulted.

## 6. MCP architecture & natural-language communication
- **Two independent MCP servers** — one per **player** — built with **FastMCP**, exposing tools for
  mutual position validation and for sending/receiving messages. A server is **not** tied to a fixed
  role: it plays thief or cop depending on the current sub-game (see §4 role alternation), and its
  prompts/resources reflect whichever role it currently holds.
- **Free text, grounded by the server.** Agents do **not** exchange a rigid numeric protocol; they
  exchange **free natural-language** messages describing intentions, local observations, or bluffs.
  To keep that free-text channel coherent, the MCP server **explains the game to the agent** — the
  rules and the turn flow — so both sides share the same ground truth before they start talking.
  This grounding is delivered through standard MCP surfaces (not hard-coded into the agent):
  - **Prompts** — prompt templates that describe the agent's role (cop vs. thief), the win/loss
    conditions, movement (8 directions), the barrier rule, and the turn order (thief → cop), so the
    LLM is primed to produce sensible free-text moves.
  - **Resources** — readable resources exposing the live rules/config (grid size, `max_moves`,
    `max_barriers`, observability mode + `view_radius`) and the current game/turn state, so the agent
    can re-read the ground truth rather than guess it. These resources reflect the **active mechanics
    the initiating server selected** for this game (§3), so the opponent always plays under the same,
    explicitly-announced rule set.
  - **Tools** — the actions: send/receive a free-text message, submit a move or barrier placement,
    and mutual position validation. Tool descriptions themselves document each option and its
    constraints (e.g. "place a barrier on your own cell; max 5 per sub-game").
  - **Identical rulebook on both servers.** The cop and thief servers expose the **same rules and
    game flow** — one shared specification. (Role differences such as "only the cop places barriers"
    are constraints within that shared rulebook, not separate rule sets.)
- **Server vs. client separation:** the **LLM lives in the client/orchestrator** (the game engine the
  students build), **not** inside the MCP server. The MCP server only exposes the tools, resources,
  and prompts above. Flow: client → LLM query (primed by the server's prompts/resources) → tool-call
  decision → MCP server executes the tool → result returned to the LLM to finish the turn.

### 6.1 Authentication (API key)
Communication between the MCP servers must be **safe and secure**, gated by a shared **API key**:
- **Key required to start a conversation.** A request to initiate a match/conversation with another
  MCP server **must present an API key**. If the presented key does **not match** an allowed key, the
  request is **rejected** and no game begins.
- **Allowed keys come from the environment.** The set of accepted API keys is configured via
  **environment variables** — never hard-coded in source and never committed to the repo (so secrets
  stay out of GitHub). Concretely:
  - `MCP_ALLOWED_API_KEYS` — comma-separated list of keys the server accepts on **inbound** requests
    (an incoming key must be a member of this set to start a conversation).
  - `MCP_API_KEY` — the key this server presents on **outbound** requests when it initiates a match.
  - Provided via a local `.env` (git-ignored) for local runs and as platform secrets in the cloud.
- **Revocable.** Removing a key from `MCP_ALLOWED_API_KEYS` immediately revokes access for that key.
- **In transit:** keys are sent over **HTTPS** (e.g. in an `Authorization` / `X-API-Key` header), so
  they are not exposed on the wire.

### 6.2 Match protocol & arbitration
There is **no central referee**. Each server runs its **own authoritative Game engine**, and the two
engines must reach the **same rulings independently — without negotiating state**. This works only if
the game is a **deterministic replicated state machine**:
- **Deterministic rules.** Given the same inputs, both engines compute byte-identical state. No engine
  uses local randomness or wall-clock in its rules; the only randomness (start positions) comes from
  the **agreed `random_seed`** (§3, §5).
- **Match setup (handshake).** Before play, the initiator proposes and the responder accepts: the
  **mechanics set**, **`random_seed`**, role assignment, and config values. Both record the agreed
  setup in their logs (§4.1). No agreement → no game.
- **Action exchange, not state exchange.** Each turn, the acting side sends its **message + action**
  (e.g. "move to `[x,y]`" / "place barrier"); each engine **independently applies** the action under
  the shared rules to advance its own copy of the state. Engines exchange *actions*, never authoritative
  positions — that keeps partial observation intact (§3).
- **Validation without negotiation.** After each action both sides compare a lightweight
  **integrity check** — e.g. a hash of the canonical state (positions + sorted barriers + round) via
  the *mutual position validation* tool. A **match = continue**; a **mismatch = divergence**, which is
  an immediate **technical loss** (§3.1) — the sub-game is void and re-run. Engines do **not** try to
  reconcile differing states.
- **Determinism requirements:** stable action ordering (thief then cop per round), a fixed coordinate
  convention (§4.1), integer-only state, and canonical serialization for the hash.

## 7. LLM architecture options
The MCP server still needs an LLM. Three approaches:
1. **Cloud LLM API** (OpenAI / Anthropic / Gemini) — simplest, stable, no local exposure. *Recommended.*
2. **Tunneled local Ollama** — expose local Ollama securely via ngrok (Traffic Policy) / Localtonet /
   Nginx reverse proxy with auth.
3. **Hybrid (outbound-only)** — keep the LLM (local Ollama) and orchestrator local; only the MCP
   servers live in the cloud; the client reaches them via outbound HTTPS. *Recommended for safe local dev.*

## 8. Deployment
- **Local first:** run both servers on `localhost` on **separate ports**; confirm a full game runs.
- **Cloud second:** deploy the MCP servers to a public cloud (e.g. Prefect Cloud).
- **Security:** API-key authentication with **revoke** capability (see §6.1 — keys from env, must
  match to start a conversation); ensure MCP URLs are publicly reachable (not blocked by corporate
  firewalls). Each group needs two URLs (cop + thief).

## 9. Actor strategy — optional Q-learning
This section concerns the **Actor** (part 5, team-specific). Reinforcement learning is **optional and
recommended only**. Teams may use heuristics, Manhattan distance, decision trees, or prompt
engineering instead. Tabular **Q-learning** (Bellman update) is suggested for an adaptive strategy
without deep nets:

$$Q(s,a) \leftarrow Q(s,a) + \alpha\,[\,r + \gamma \max_{a'} Q(s',a') - Q(s,a)\,]$$

See the assignment brief for the minimal reference implementation.

## 10. Reporting
- At the end of all 6 **valid** sub-games, exactly **one** designated agent emails the report to
  **`rmisegal+uoh26b@gmail.com`**. Because roles alternate, "the cop" is not a fixed sender — the
  **initiating server** is the designated sender for the internal game; in the bonus game **each team
  sends its own** identical report from its designated sender.
- **Send once.** The report is emailed a single time, only after 6 valid sub-games complete. Re-runs
  for technical losses do **not** trigger extra emails; the sender must dedupe so the grading inbox
  receives exactly one final report per game.
- Use the **Gmail API** (token-based auth, not username/password) for reliability.
- The email body must contain **only the structured JSON report — no free text** — to allow automated
  ingestion.
- **Technical-loss** sub-games (§3.1) are **void**, carry no score, and must be re-run to complete the
  quota of 6 valid sub-games.
- **Internal-game `totals` are informational.** The internal game is a team playing its own two
  agents to demonstrate the pipeline; `totals` is broken down by role (`cop`/`thief`) and there is no
  "winner" of the internal game.
- Two report shapes. Both carry a `sub_games` array; each element is a **sub-game record** (below),
  derived from that sub-game's log (§4.1). Reports also carry a `played_at` timestamp (ISO-8601, in
  the report `timezone`). The `students` array holds objects of the form
  `{ "name": "...", "id": "..." }`.

**Per-sub-game record** (one element of the `sub_games` array):
```json
{
  "sub_game": 1,
  "initiator_role": "thief",
  "cop": "Team-Beta",
  "thief": "Team-Alpha",
  "winner": "cop",
  "win_reason": "capture",
  "moves": 14,
  "barriers_used": 3,
  "scores": { "cop": 20, "thief": 5 }
}
```
`win_reason` ∈ `"capture"` | `"thief_trapped"` | `"thief_survived"` | `"cop_trapped"` |
`"technical_loss"`. For the **internal** game, `cop`/`thief` name the two player servers; for the
**bonus** game they name the two competing teams.

**Internal game JSON** — single GitHub link + two MCP URLs (cop, thief):
```json
{
  "group_name": "Team-Alpha",
  "students": [],
  "github_repo": "https://github.com/team-alpha/marl-cop-thief",
  "cop_mcp_url": "https://cop-mcp-alpha.prefect.run",
  "thief_mcp_url": "https://thief-mcp-alpha.prefect.run",
  "timezone": "Asia/Jerusalem",
  "played_at": "2026-06-22T14:30:00+03:00",
  "sub_games": [
    { "sub_game": 1, "initiator_role": "thief", "cop": "player_b", "thief": "player_a", "winner": "cop",   "win_reason": "capture",        "moves": 14, "barriers_used": 3, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 2, "initiator_role": "cop",   "cop": "player_a", "thief": "player_b", "winner": "thief", "win_reason": "thief_survived", "moves": 25, "barriers_used": 5, "scores": { "cop": 5,  "thief": 10 } },
    { "sub_game": 3, "initiator_role": "thief", "cop": "player_b", "thief": "player_a", "winner": "cop",   "win_reason": "thief_trapped",  "moves": 9,  "barriers_used": 5, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 4, "initiator_role": "cop",   "cop": "player_a", "thief": "player_b", "winner": "cop",   "win_reason": "capture",        "moves": 17, "barriers_used": 2, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 5, "initiator_role": "thief", "cop": "player_b", "thief": "player_a", "winner": "thief", "win_reason": "thief_survived", "moves": 25, "barriers_used": 4, "scores": { "cop": 5,  "thief": 10 } },
    { "sub_game": 6, "initiator_role": "cop",   "cop": "player_a", "thief": "player_b", "winner": "cop",   "win_reason": "capture",        "moves": 11, "barriers_used": 1, "scores": { "cop": 20, "thief": 5 } }
  ],
  "totals": {
    "cop": 90,
    "thief": 40
  }
}
```

**Inter-group bonus JSON** — both teams, two GitHub links, four MCP URLs, `mutual_agreement` flag:
```json
{
  "report_type": "bonus_game",
  "groups": {
    "group_1": "Team-Alpha",
    "group_2": "Team-Beta"
  },
  "github_repo_group_1": "https://github.com/team-alpha/marl-cop-thief",
  "github_repo_group_2": "https://github.com/team-beta/marl-cop-thief",
  "mcp_url_group_1_cop": "https://cop-mcp-alpha.prefect.run",
  "mcp_url_group_1_thief": "https://thief-mcp-alpha.prefect.run",
  "mcp_url_group_2_cop": "https://cop-mcp-beta.prefect.run",
  "mcp_url_group_2_thief": "https://thief-mcp-beta.prefect.run",
  "timezone": "Asia/Jerusalem",
  "played_at": "2026-06-22T14:30:00+03:00",
  "students_group_1": [],
  "students_group_2": [],
  "sub_games": [
    { "sub_game": 1, "cop": "Team-Alpha", "thief": "Team-Beta",  "winner": "cop",   "win_reason": "capture",        "moves": 12, "barriers_used": 2, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 2, "cop": "Team-Alpha", "thief": "Team-Beta",  "winner": "cop",   "win_reason": "capture",        "moves": 16, "barriers_used": 4, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 3, "cop": "Team-Alpha", "thief": "Team-Beta",  "winner": "thief", "win_reason": "thief_survived", "moves": 25, "barriers_used": 3, "scores": { "cop": 5,  "thief": 10 } },
    { "sub_game": 4, "cop": "Team-Beta",  "thief": "Team-Alpha", "winner": "cop",   "win_reason": "capture",        "moves": 10, "barriers_used": 1, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 5, "cop": "Team-Beta",  "thief": "Team-Alpha", "winner": "cop",   "win_reason": "capture",        "moves": 19, "barriers_used": 5, "scores": { "cop": 20, "thief": 5 } },
    { "sub_game": 6, "cop": "Team-Beta",  "thief": "Team-Alpha", "winner": "cop",   "win_reason": "thief_trapped",  "moves": 8,  "barriers_used": 5, "scores": { "cop": 20, "thief": 5 } }
  ],
  "totals_by_group": {
    "Team-Alpha": 60,
    "Team-Beta": 80
  },
  "bonus_claim": {
    "Team-Alpha": 7,
    "Team-Beta": 10
  },
  "mutual_agreement": true
}
```

## 11. Deliverables
- **Public GitHub repository** with all source code.
- **Scientific `README.md`** at the repo root, including:
  - **Formal modeling** as a DecPOMDP: $\langle n, S, \{A_i\}, P, R, \{\Omega_i\}, O, \gamma \rangle$,
    defining state and observation spaces (assuming the default partial-observation case).
  - **Orchestration analysis:** managing free natural-language communication without a predefined
    protocol, handling linguistic ambiguity, ensuring mutual understanding.
  - **Visualization & evidence:** learning-curve graphs (if Q-table used), GUI screenshots of the
    game, and CLI logs proving correct communication with the cloud MCP servers.

## 12. (Optional) Bonus inter-group competition
Worth up to **10 points** toward the final project; must be submitted within **one week** of the
assignment's release.
- **Role split (3-then-3, deliberately *not* the alternating schedule of §4):**
  sub-games 1–3 → Team A cop vs. Team B thief; sub-games 4–6 → Team B cop vs. Team A thief. The
  internal game alternates roles every sub-game; the bonus game uses this fixed 3+3 split because the
  assignment mandates it.
- **Agreed mechanics.** Before the series, both teams must agree on the mechanics set, `random_seed`
  per sub-game, and config (§3, §6.2) — neither side may impose terms unilaterally.
- Both teams email reports with **identical results**. Equality is checked on a **canonical
  normalization**, not raw bytes: the `sub_games` records (per `sub_game`: roles, `winner`,
  `win_reason`, `moves`, `barriers_used`, `scores`) and the score totals must match exactly.
  Cosmetic fields (whitespace, key order, `students`, `played_at`, URLs) are ignored in the
  comparison.
- Scoring: higher cumulative score → 10 pts, loser → 7 pts, tie → 5 pts each; final bonus = average
  across all valid series. Disagreement on the canonical fields voids the bonus (0 for both).
