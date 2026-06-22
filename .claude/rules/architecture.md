# Architecture Rules

## SDK Layer
All business logic is exposed through a single SDK entry point (`src/<package>/sdk/sdk.py`). CLI and any external callers must go through the SDK — never call services or agents directly.

## API Gatekeeper
All LLM API calls must go through the Gatekeeper (`src/<package>/shared/gatekeeper.py`). It handles rate limiting (read from `config/rate_limits.json`), request queuing, retries with exponential backoff, and per-call logging. No agent or service calls the LLM API directly.

## OOP & Thread Safety
- Use inheritance and mixins for shared agent and reviewer behaviour — no copy-paste between agents.
- Any component running reviewers or agents in parallel must use locks or queues for shared state.

## Extension Points
Each major component must expose a hook or registration mechanism so new agents/reviewers can be added without modifying core orchestration code.
