"""LLM backend call helpers extracted from Gatekeeper to stay under 150 lines."""

from __future__ import annotations

from typing import Any

import httpx


def call_anthropic(
    client: object,
    model: str,
    messages: list[dict[str, str]],
    system: str | None,
    max_tokens: int,
) -> str:
    """Call the Anthropic API and return the response text.

    Args:
        client: anthropic.Anthropic() client instance.
        model: Anthropic model ID.
        messages: Conversation messages.
        system: Optional system prompt string.
        max_tokens: Response token limit.

    Returns:
        Assistant response text.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    usage = response.usage
    print(  # noqa: T201
        f"[gatekeeper] model={model} in={usage.input_tokens} out={usage.output_tokens}"
    )
    return response.content[0].text


def call_ollama(
    http_client: httpx.Client,
    url: str,
    model: str,
    messages: list[dict[str, str]],
    system: str | None,
) -> str:
    """Call the local Ollama /api/chat endpoint and return the response text.

    Args:
        http_client: httpx.Client instance with keep-alive connection.
        url: Full Ollama API URL (e.g. http://localhost:11434/api/chat).
        model: Ollama model name.
        messages: Conversation messages.
        system: Optional system prompt (prepended as system role message).

    Returns:
        Assistant response text.
    """
    chat_messages: list[dict[str, str]] = []
    if system:
        chat_messages.append({"role": "system", "content": system})
    chat_messages.extend(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "keep_alive": "10m",
    }
    response = http_client.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    in_tok = data.get("prompt_eval_count", "?")
    out_tok = data.get("eval_count", "?")
    print(  # noqa: T201
        f"[gatekeeper] model={model} (ollama) in={in_tok} out={out_tok}"
    )
    return data["message"]["content"]
