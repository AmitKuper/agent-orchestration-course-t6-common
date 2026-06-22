# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Read `docs/rules.md` before writing any code. All code in this repo must comply with those rules.**

## Project Overview

**Cop & Thief: Dual AI-Agent Pursuit over MCP** — HW6 for an AI Agent Orchestration course. Two autonomous AI agents (Cop and Thief) play a pursuit game on a 2D grid, communicating in free natural language via two independent MCP servers (one per agent). Full spec in `docs/PRD.md`.

## Package Management

Use `uv` exclusively — no pip, no poetry:
```
uv add <package>
uv run <command>
uv sync
```
Always commit `uv.lock` alongside `pyproject.toml`. All dependencies declared in `pyproject.toml` only.

## Linting & Quality

- **Zero Ruff violations** required. Run: `uv run ruff check .`
- Test coverage target: ≥ 85%. Run: `uv run pytest`
- Single test file per module, under `unit/` and `integration/` folders.

## Code Rules (from `docs/rules.md`)

- **150-line max** per file. Extract helpers, apply single responsibility.
- Every method/class/function must have a docstring. Comments explain *why*, not *what*.
- No code duplication — implement once, reuse via inheritance/mixins.
- Commit format: `Feature: ...` | `BugFix: ...` | `Refactor: ...` | `Docs: ...`
- Track token usage per phase in `docs/cost.md`. Update `docs/TODO.md` after every progress session.

## Architecture

The project has 5 parts — parts 1–4 are **shared** between teams; part 5 is **team-specific**:

| Part | Name | Description |
|------|------|-------------|
| 1 | **Game** | Rules, grid state machine, move validation, capture/barrier detection, scoring |
| 2 | **Agent** | Parser/translator: NL messages ↔ game commands + state rendering |
| 3 | **MCP server** | FastMCP tools (send/receive messages, mutual position validation), prompts, resources |
| 4 | **Gmail** | Send JSON game report via Gmail API (token-based auth) |
| 5 | **Actor** | Strategy/decision-making brain — the only team-specific part |

**Key distinction:** `Agent` = interpreter (parsing + rendering); `Actor` = strategy (what to do next).

### Architecture Patterns

- **SDK layer** (`src/<package>/sdk/sdk.py`): all business logic exposed through a single SDK entry point. CLI and external callers go through SDK only — never call services/agents directly.
- **API Gatekeeper** (`src/<package>/shared/gatekeeper.py`): all LLM API calls go through the Gatekeeper (rate limiting from `config/rate_limits.json`, retries, logging). No agent calls LLM directly.
- Parallel components must use locks/queues for shared state.

### MCP Architecture

- Two independent MCP servers (one per player), built with **FastMCP**.
- Server is NOT tied to a fixed role — it plays cop or thief depending on the sub-game.
- **LLM lives in the client/orchestrator**, not inside the MCP server.
- Servers expose: **Prompts** (role + rules grounding), **Resources** (live config + game state), **Tools** (move/barrier/message actions).
- Both servers expose the **same shared rulebook**.

### Game Engine (Replicated State Machine)

- No central referee — each server runs its own authoritative `Game` engine.
- Engines exchange **actions**, never state (preserves partial observation).
- Shared `random_seed` agreed at match setup → both engines derive identical start positions.
- After each action, engines compare a **state hash** via the mutual-position-validation tool. Mismatch = technical loss (sub-game void, re-run).
- **Coordinate convention**: `[x, y]` 0-indexed, origin top-left; `x` = column (rightward), `y` = row (downward).

### Observability

- Default: `partial_observation: true` — each agent sees only its own position + barriers/opponent within `view_radius` (Chebyshev distance = 2).
- Hidden state must **never leak** into the Actor.

## Configuration

All parameters in `config.json`/`config.yaml` — **no hard-coding**. Key defaults:

| Parameter | Default |
|-----------|---------|
| `grid_size` | `[5, 5]` |
| `max_moves` | `25` (rounds per sub-game) |
| `num_games` | `6` |
| `max_barriers` | `5` |
| `partial_observation` | `true` |
| `view_radius` | `2` |
| `turn_timeout_seconds` | `30` |
| `max_illegal_retries` | `2` |
| `max_consecutive_forfeits` | `3` |

## Secrets & Security

- `MCP_ALLOWED_API_KEYS` — comma-separated list of accepted inbound keys.
- `MCP_API_KEY` — key this server presents on outbound requests.
- Store in `.env` (git-ignored). Never commit secrets. Use `.env.example` as template.
- Keys sent over HTTPS (Authorization / X-API-Key header).

## Scoring & Match Structure

- 6 sub-games per series; roles alternate each sub-game (initiator starts as thief).
- Cop wins (capture or thief_trapped): cop 20 pts / thief 5 pts.
- Thief wins (survived or cop_trapped): cop 5 pts / thief 10 pts.
- Technical loss → void, no score, re-run.

## Reporting

- After all 6 valid sub-games, **initiating server** emails JSON report to `rmisegal+uoh26b@gmail.com`.
- Gmail API with token-based auth (not username/password).
- Email body: **only the structured JSON** — no free text.
- Report schema: see `docs/PRD.md` §10 for exact JSON shape.

## Mandatory Deliverables

- `README.md` — formal DecPOMDP modeling, orchestration analysis, visualization/evidence.
- `docs/PRD_<component>.md` per major subsystem.
- `notebooks/` — cost analysis and sensitivity analysis notebooks.
- `assets/` — architecture diagrams, screenshots.
- `config/rate_limits.json` and `config/setup.json`.
- `docs/cost.md` — token usage tracking per phase.
- `docs/TODO.md` — kept current; update in same commit as work.

> **Before submitting any code, re-read `docs/rules.md` and verify full compliance.**
