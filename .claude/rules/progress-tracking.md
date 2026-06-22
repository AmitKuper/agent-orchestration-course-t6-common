# Progress Tracking Rules

## docs/TODO.md
- Update after every progress session — never let it drift from reality.
- Mark completed items `[x]` and set phase status to `✅ Complete` with the commit hash.
- Mark in-progress items `🚧 In Progress`.
- Update task descriptions when scope changes mid-phase rather than silently diverging.
- TODO.md updates must be in the same commit as the work they describe (or a follow-up `Docs: Update TODO progress` commit).

## docs/cost.md
- Record token usage for every step, phase, or TODO item.
- Format: `Tokens: ~X input / ~Y output` (or `~X total` if breakdown unavailable).
- Include cumulative totals per phase.
- Use actual token counts from API responses when available; otherwise estimate.
