# Configuration & Security Rules

## Configuration
- All configurable parameters go in config files (JSON or YAML) — no hard-coding.
- `config/rate_limits.json` — LLM rate limit config; read exclusively by the Gatekeeper.
- `config/setup.json` — application setup (default paths, log levels, compile options).

## Secrets
- API keys, passwords, and secrets go in environment variables only — never committed to code.
- Use `.env.example` as a template for required variables.
- Ensure `.gitignore` excludes `.env` and sensitive files.
