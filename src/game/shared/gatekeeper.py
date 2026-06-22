"""API Gatekeeper — rate-limited, retried LLM call wrapper.

All LLM calls must go through this module. No agent or service calls the API directly.
Rate limits are read from config/rate_limits.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import anthropic

_DEFAULT_RATE_LIMITS_PATH = Path("config/rate_limits.json")
_DEFAULT_MODEL = "claude-opus-4-8"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def _load_rate_limits(path: Path) -> dict[str, Any]:
    """Load rate limits from JSON config file."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


class Gatekeeper:
    """Rate-limited, retried wrapper around the Anthropic API.

    Handles per-model RPM/TPM limits, exponential backoff on 429s,
    and logs token usage to stdout for cost tracking.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        rate_limits_path: Path = _DEFAULT_RATE_LIMITS_PATH,
    ) -> None:
        """Initialise the Gatekeeper for the given model.

        Args:
            model: Anthropic model ID to use.
            rate_limits_path: Path to rate_limits.json config.
        """
        self.model = model
        self._client = anthropic.Anthropic()
        limits = _load_rate_limits(rate_limits_path).get(model, {})
        self._rpm: int = limits.get("rpm", 50)
        self._tpm: int = limits.get("tpm", 100000)
        self._last_call: float = 0.0

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
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system

        for attempt in range(_MAX_RETRIES):
            self._enforce_rate_limit()
            try:
                response = self._client.messages.create(**kwargs)
                usage = response.usage
                print(  # noqa: T201 — intentional cost log
                    f"[gatekeeper] model={self.model} "
                    f"in={usage.input_tokens} out={usage.output_tokens}"
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                wait = _BACKOFF_BASE ** attempt
                time.sleep(wait)
            except anthropic.APIError as exc:
                if attempt == _MAX_RETRIES - 1:
                    msg = f"LLM call failed after {_MAX_RETRIES} attempts: {exc}"
                    raise RuntimeError(msg) from exc
                time.sleep(_BACKOFF_BASE ** attempt)
        raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} attempts")
