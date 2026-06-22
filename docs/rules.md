# Code Quality Rules

## 1. Code Organization & File Size

Scripts/code files must not exceed **150 lines**. Refactor as follows:
- Extract helper functions into separate modules
- Apply single responsibility principle per class (use mixins for shared behavior)
- Split large files 50/50 (e.g., Input handling + Output handling in separate files)
- Extract magic numbers and constants to `constants.py`
- Move reusable logic to separate utility modules

## 2. Comments & Documentation

- **Code comments**: Explain *why*, not *what*; only where the logic isn't self-evident
- **Docstrings**: Every method, class, and function must have detailed docstrings
- **Naming**: Use descriptive, theory-grounded names for classes, parameters, and methods

## 3. Testing & Test Documentation

- Every module must include a test module/document alongside implementation
- Document test scenarios, edge cases, and validation test plans
- Maintain clear test naming and organization (unit/, integration/ folders)

## 4. Code Reuse & Design

- No code duplication; implement each feature once with single responsibility
- Follow OOP principles; use inheritance and mixins for shared functionality
- Avoid copy-paste development

## 5. Testing & Quality

- Create unit tests for each method and class
- Target test coverage ≥ 85%
- Document edge cases and error handling scenarios
- Zero Ruff violations

## 6. Configuration & Security

- **Configurable parameters** → store in config files (JSON or YAML)
- **Secrets, API keys, passwords** → environment variables only, never committed to code
- Use `.env.example` as a template for required variables
- Ensure `.gitignore` excludes `.env` and sensitive files

## 7. Git Workflow

- Write clear, descriptive commit messages:
  - `Feature: <feature_name>` for new features
  - `BugFix: <issue_description>` for bug fixes
  - `Refactor: <scope>` for refactoring
  - `Docs: <change>` for documentation
- Keep commits atomic and focused on a single logical change
- **Never push to the BugsInPy submodule** — it is a read-only reference; push only to the main project remote

## 8. Token Usage Cost Tracking

- **Record token usage for every step, phase, or TODO item** in `docs/cost.md` (a dedicated cost tracking file)
- Use actual token counts from API responses when available; otherwise estimate as closely as possible
- Format: `Tokens: ~X input / ~Y output` (or `Tokens: ~X total` if breakdown unavailable)
- Include cumulative totals per phase so overall cost is trackable
- Estimates should be based on approximate prompt + response sizes when exact counts are not accessible

## 9. Progress Tracking & TODO Maintenance

- **Update `docs/TODO.md` after every progress**: do not let it drift from reality
- When a task or phase is completed:
  - Mark checklist items with `[x]`
  - Update phase status to `✅ Complete` with the commit hash (e.g., `commit 37080b2`)
  - Add brief outcome notes if relevant (e.g., test count, coverage achieved, deviations from plan)
- When a task is started but not finished, mark it `🚧 In Progress`
- When scope changes mid-phase, update the task description rather than silently diverging
- TODO.md updates should be part of the same commit as the work they describe, OR a follow-up `Docs: Update TODO progress` commit; never leave them uncommitted across sessions

## 10. Package & Dependency Management

- **Use `uv`** (not pip, not poetry) for all package management — `uv add`, `uv run`, `uv sync`
- Commit `uv.lock` alongside `pyproject.toml` — never commit without a matching lock file
- **Semantic versioning** must be kept in sync across three locations: `src/<package>/shared/version.py`, `pyproject.toml`, and `config/rate_limits.json`
- `pyproject.toml` is the single source of build metadata, Ruff config, and pytest config
- Never use `requirements.txt`; all dependencies declared in `pyproject.toml`

## 11. Architecture Patterns

- **SDK layer** (`src/<package>/sdk/sdk.py`): all business logic is exposed through a single SDK entry point. The CLI and any external callers must go through the SDK — never call services or agents directly.
- **API Gatekeeper** (`src/<package>/shared/gatekeeper.py`): all LLM API calls (Claude / AgentCrew) must go through the Gatekeeper. It handles rate limiting (read from `config/rate_limits.json`), request queuing, retries with exponential backoff, and per-call logging. No agent or service calls the LLM API directly.
- **OOP design**: use inheritance and mixins for shared agent and reviewer behaviour. No copy-paste between agents. Reviewer base class defines the verdict contract; each reviewer inherits it.
- **Thread safety**: any component that runs reviewers or agents in parallel must use locks or queues for shared state (manifest writes, cost accumulation, verdict aggregation).
- **Extension points**: each major component (content agents, reviewers, assembler) must expose a hook or registration mechanism so new agents/reviewers can be added without modifying core orchestration code.

## 12. Mandatory Deliverables

- **`README.md`** at project root — mandatory; must include installation, quick-start, usage, configuration, module reference, troubleshooting, and project structure sections
- **`docs/PRD_<component>.md`** — one component-level PRD per major subsystem (e.g., `PRD_review_crew.md`, `PRD_content_agents.md`, `PRD_assembler.md`); each covers algorithm description, input/output contracts, performance constraints, and test scenarios
- **`notebooks/`** — at least one Jupyter notebook with cost analysis (token usage per phase, optimization opportunities) and sensitivity analysis (effect of config parameters on output quality)
- **`assets/`** — architecture diagrams, sample output screenshots, and any other visual documentation
- **`config/rate_limits.json`** — externalized LLM rate limit configuration (requests/min, tokens/min, retry policy); read exclusively by the Gatekeeper
- **`config/setup.json`** — externalized application setup (default paths, log levels, compile options); never embed these values in source code
