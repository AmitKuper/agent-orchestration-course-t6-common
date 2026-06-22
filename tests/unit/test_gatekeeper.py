"""Unit tests for game.shared.gatekeeper."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from game.shared.gatekeeper import Gatekeeper, _load_rate_limits


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
    """Build a Gatekeeper with a mocked Anthropic client."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "limits.json"
        p.write_text(json.dumps({"claude-opus-4-8": {"rpm": rpm, "tpm": 100000}}))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
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
             patch("time.sleep"):  # skip actual sleep
            gk = Gatekeeper(rate_limits_path=p)
            result = gk.call([{"role": "user", "content": "hi"}])
    assert result == "OK"
    assert mock_client.messages.create.call_count == 2
