"""Unit tests for game.shared.gatekeeper."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from game.shared.gatekeeper import Gatekeeper, _default_model, _load_rate_limits


def test_load_rate_limits_missing_file_returns_empty() -> None:
    """Returns empty dict when file does not exist."""
    result = _load_rate_limits(Path("/nonexistent/path.json"))
    assert result == {}


def test_load_rate_limits_reads_config() -> None:
    """Reads and parses an existing JSON config file."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "limits.json"
        p.write_text(json.dumps({"claude-opus-4-8": {"rpm": 30, "tpm": 50000}}))
        result = _load_rate_limits(p)
        assert result["claude-opus-4-8"]["rpm"] == 30


def _make_gatekeeper(rpm: int = 60) -> tuple[Gatekeeper, MagicMock]:
    """Build an Anthropic-backed Gatekeeper with a mocked Anthropic client."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "limits.json"
        p.write_text(json.dumps({"claude-opus-4-8": {"rpm": rpm, "tpm": 100000}}))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            gk = Gatekeeper(model="claude-opus-4-8", rate_limits_path=p)
            return gk, mock_client


def test_gatekeeper_call_returns_text() -> None:
    """call() returns the assistant's text."""
    gk, mock_client = _make_gatekeeper()
    result = gk.call([{"role": "user", "content": "hi"}])
    assert result == "Hello"


def test_gatekeeper_call_passes_system_prompt() -> None:
    """System prompt is forwarded to the API when provided."""
    gk, mock_client = _make_gatekeeper()
    gk.call([{"role": "user", "content": "hi"}], system="You are a cop.")
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs.get("system") == "You are a cop."


def test_gatekeeper_call_no_system_when_none() -> None:
    """No system key in API call when system is None."""
    gk, mock_client = _make_gatekeeper()
    gk.call([{"role": "user", "content": "hi"}])
    call_kwargs = mock_client.messages.create.call_args[1]
    assert "system" not in call_kwargs


def test_default_model_anthropic_when_key_set() -> None:
    """_default_model returns the Anthropic model when ANTHROPIC_API_KEY is set."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
        assert _default_model() == "claude-opus-4-8"


def test_default_model_ollama_when_no_key() -> None:
    """_default_model returns the Ollama default when ANTHROPIC_API_KEY is absent."""
    env = {"OLLAMA_MODEL": ""}
    with patch.dict("os.environ", env, clear=False), \
         patch.dict("os.environ", {}, clear=False):
        # Remove ANTHROPIC_API_KEY if present
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OLLAMA_MODEL", None)
        assert _default_model() == "llama3.2"


def test_gatekeeper_uses_ollama_backend() -> None:
    """Gatekeeper selects Ollama when ANTHROPIC_API_KEY is absent."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["OLLAMA_BASE_URL"] = "http://localhost:11434"
    with patch.dict("os.environ", env, clear=True):
        gk = Gatekeeper()
    assert not gk._use_anthropic
    assert "11434" in gk._ollama_url


def test_gatekeeper_ollama_call_returns_text() -> None:
    """Ollama backend: call() returns the message content from the API response."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["OLLAMA_BASE_URL"] = "http://localhost:11434"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "Going east."},
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    mock_response.raise_for_status = MagicMock()

    with patch.dict("os.environ", env, clear=True), \
         patch("httpx.post", return_value=mock_response):
        gk = Gatekeeper()
        result = gk.call([{"role": "user", "content": "hi"}])

    assert result == "Going east."


def test_gatekeeper_ollama_prepends_system_message() -> None:
    """System prompt is sent as a system-role message in the Ollama payload."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["OLLAMA_BASE_URL"] = "http://localhost:11434"

    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": "ok"}, "usage": {}}
    mock_response.raise_for_status = MagicMock()

    with patch.dict("os.environ", env, clear=True), \
         patch("httpx.post", return_value=mock_response) as mock_post:
        gk = Gatekeeper()
        gk.call([{"role": "user", "content": "hi"}], system="You are a cop.")

    payload = mock_post.call_args[1]["json"]
    assert payload["messages"][0] == {"role": "system", "content": "You are a cop."}


def test_gatekeeper_retries_on_rate_limit() -> None:
    """RateLimitError triggers a retry; succeeds on second attempt."""
    import anthropic

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "limits.json"
        p.write_text("{}")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="OK")]
        mock_response.usage = MagicMock(input_tokens=1, output_tokens=1)
        mock_client.messages.create.side_effect = [
            anthropic.RateLimitError("rate limited", response=MagicMock(), body={}),
            mock_response,
        ]
        with patch("anthropic.Anthropic", return_value=mock_client), \
             patch("time.sleep"), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            gk = Gatekeeper(rate_limits_path=p)
            result = gk.call([{"role": "user", "content": "hi"}])
    assert result == "OK"
    assert mock_client.messages.create.call_count == 2
