"""API Gatekeeper — rate-limited, retried LLM call wrapper.

All LLM calls must go through this module. No agent or service calls the API directly.
Rate limits are read from config/rate_limits.json.
Backend: ANTHROPIC_API_KEY set → Anthropic; otherwise → Ollama (OLLAMA_BASE_URL).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import anthropic
import httpx

from game.shared.llm_backends import call_anthropic, call_ollama

_DEFAULT_RATE_LIMITS_PATH = Path("config/rate_limits.json")
_DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
_DEFAULT_OLLAMA_MODEL = "llama3.2"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def _load_rate_limits(path: Path) -> dict[str, Any]:
    """Load rate limits from JSON config file."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _default_model() -> str:
    """Return the default model ID based on the active backend."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _DEFAULT_ANTHROPIC_MODEL
    return os.environ.get("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)


class Gatekeeper:
    """Rate-limited, retried wrapper around the LLM API (Anthropic or Ollama).

    Backend selection (checked at construction time):
    - ANTHROPIC_API_KEY is set → Anthropic cloud API.
    - Otherwise → local Ollama at OLLAMA_BASE_URL (default http://localhost:11434).
    """

    def __init__(
        self,
        model: str | None = None,
        rate_limits_path: Path = _DEFAULT_RATE_LIMITS_PATH,
    ) -> None:
        """Initialise the Gatekeeper, selecting backend from environment.

        Args:
            model: LLM model ID. Defaults to claude-opus-4-8 or llama3.2 per backend.
            rate_limits_path: Path to rate_limits.json config.
        """
        self._use_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model or _default_model()
        limits = _load_rate_limits(rate_limits_path).get(self.model, {})
        self._rpm: int = limits.get("rpm", 50)
        self._tpm: int = limits.get("tpm", 100000)
        self._last_call: float = 0.0
        if self._use_anthropic:
            self._anthropic = anthropic.Anthropic()
        else:
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            self._ollama_url = base.rstrip("/") + "/api/chat"
            # Persistent client keeps the TCP connection alive between turns,
            # avoiding per-call connection setup overhead.
            self._http = httpx.Client(timeout=120.0)

    def _enforce_rate_limit(self) -> None:
        """Sleep if necessary to stay within RPM limit."""
        min_gap = 60.0 / self._rpm
        elapsed = time.monotonic() - self._last_call
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        self._last_call = time.monotonic()

    def call(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 512,
    ) -> str:
        """Make a rate-limited, retried LLM call.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            system: Optional system prompt string.
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's text response.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        for attempt in range(_MAX_RETRIES):
            self._enforce_rate_limit()
            try:
                if self._use_anthropic:
                    return call_anthropic(
                        self._anthropic, self.model, messages, system, max_tokens
                    )
                return call_ollama(self._http, self._ollama_url, self.model, messages, system)
            except anthropic.RateLimitError:
                time.sleep(_BACKOFF_BASE**attempt)
            except (anthropic.APIError, httpx.HTTPError) as exc:
                if attempt == _MAX_RETRIES - 1:
                    msg = f"LLM call failed after {_MAX_RETRIES} attempts: {exc}"
                    raise RuntimeError(msg) from exc
                time.sleep(_BACKOFF_BASE**attempt)
        raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} attempts")
