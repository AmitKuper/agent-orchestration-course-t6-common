# Code Quality Rules

## File Size
- Max **150 lines** per file. Extract helpers into separate modules; apply single responsibility per class.
- Extract magic numbers and constants to `constants.py`.

## Comments & Documentation
- Docstrings required on every method, class, and function.
- Comments explain *why*, not *what* — only where logic isn't self-evident.
- Use descriptive, theory-grounded names for classes, parameters, and methods.

## Code Reuse & Design
- No code duplication — implement each feature once.
- Follow OOP principles; use inheritance and mixins for shared functionality.

## Testing
- Every module must have a test module alongside it; organize under `unit/` and `integration/` folders.
- Target test coverage ≥ 85%.
- Zero Ruff violations (`uv run ruff check .`).
