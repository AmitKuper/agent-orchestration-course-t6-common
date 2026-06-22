# Git Workflow Rules

## Commit Messages
- `Feature: <feature_name>` — new features
- `BugFix: <issue_description>` — bug fixes
- `Refactor: <scope>` — refactoring
- `Docs: <change>` — documentation

Keep commits atomic and focused on a single logical change.

## Package Management
- Use `uv` exclusively (`uv add`, `uv run`, `uv sync`) — not pip, not poetry.
- Always commit `uv.lock` alongside `pyproject.toml`.
- `pyproject.toml` is the single source of build metadata, Ruff config, and pytest config.
- Never use `requirements.txt`.

## Versioning
Semantic versioning must stay in sync across: `src/<package>/shared/version.py`, `pyproject.toml`, and `config/rate_limits.json`.
