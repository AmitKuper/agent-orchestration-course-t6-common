"""ToolCaller — drives LLM tool-use loops via Gatekeeper with Anthropic/Ollama support.

The LLM is called repeatedly until it stops requesting tool calls or the step
budget is exhausted. Blocking HTTP calls are wrapped in asyncio.to_thread so the
orchestrator's event loop is not stalled.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from game.shared.mcp_tool_format import (
    LLMResponse,
    anthropic_tool_result_messages,
    ollama_tool_result_messages,
    parse_anthropic_response,
    parse_ollama_response,
    to_anthropic_tools,
    to_ollama_tools,
)

if TYPE_CHECKING:
    from game.shared.gatekeeper import Gatekeeper

_MAX_TOOL_STEPS = 10

ToolExecutor = Callable[[str, dict], Awaitable[str]]


class ToolCaller:
    """Drives an LLM tool-use loop against Anthropic or Ollama backends.

    Calls the LLM with tool definitions, executes tool calls via an async
    executor, and appends results back into the conversation until the model
    stops requesting tools or _MAX_TOOL_STEPS is exhausted.
    """

    def __init__(self, gatekeeper: Gatekeeper) -> None:
        """Initialise with a configured Gatekeeper instance.

        Args:
            gatekeeper: Rate-limited LLM wrapper that selects the backend.
        """
        self._gk = gatekeeper

    async def call_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_executor: ToolExecutor,
        system: str | None = None,
    ) -> list[dict]:
        """Run the LLM in a tool-use loop, returning the final conversation.

        Args:
            messages: Initial conversation messages.
            tools: Unified tool definitions (Anthropic input_schema convention).
            tool_executor: Async callable (tool_name, args) -> result_str.
            system: Optional system prompt.

        Returns:
            Full conversation including all LLM responses and tool results.
        """
        conv = list(messages)
        for _ in range(_MAX_TOOL_STEPS):
            resp = await asyncio.to_thread(self._raw_call, conv, tools, system)
            if not resp.has_tool_calls:
                conv.append({"role": "assistant", "content": resp.content})
                break
            results = [
                await tool_executor(tc.name, tc.arguments)
                for tc in resp.tool_calls
            ]
            if self._gk._use_anthropic:
                conv.extend(anthropic_tool_result_messages(
                    resp.tool_calls, results, resp.raw.content
                ))
            else:
                conv.extend(ollama_tool_result_messages(
                    resp.tool_calls, results, resp.content
                ))
        return conv

    def _raw_call(
        self, messages: list[dict], tools: list[dict], system: str | None
    ) -> LLMResponse:
        """Make one LLM call with tool definitions, honouring rate limits.

        Accesses _gk._anthropic / _gk._ollama_url directly so we can pass
        tool definitions that the Gatekeeper.call() text path does not support.

        Args:
            messages: Current conversation messages.
            tools: Unified tool definitions.
            system: Optional system prompt.

        Returns:
            Parsed LLMResponse with any tool calls.
        """
        self._gk._enforce_rate_limit()
        if self._gk._use_anthropic:
            return self._call_anthropic(messages, tools, system)
        return self._call_ollama(messages, tools, system)

    def _call_anthropic(
        self, messages: list[dict], tools: list[dict], system: str | None
    ) -> LLMResponse:
        """Call Anthropic messages.create with tool support.

        Args:
            messages: Conversation messages.
            tools: Unified tool definitions.
            system: Optional system prompt.

        Returns:
            Parsed LLMResponse.
        """
        kwargs: dict[str, Any] = {
            "model": self._gk.model,
            "messages": messages,
            "tools": to_anthropic_tools(tools),
            "max_tokens": 1024,
        }
        if system:
            kwargs["system"] = system
        resp = self._gk._anthropic.messages.create(**kwargs)
        return parse_anthropic_response(resp)

    def _call_ollama(
        self, messages: list[dict], tools: list[dict], system: str | None
    ) -> LLMResponse:
        """Call Ollama /api/chat with tool support.

        Args:
            messages: Conversation messages.
            tools: Unified tool definitions.
            system: Optional system prompt.

        Returns:
            Parsed LLMResponse.
        """
        import httpx

        chat_msgs: list[dict] = []
        if system:
            chat_msgs.append({"role": "system", "content": system})
        chat_msgs.extend(messages)
        payload: dict[str, Any] = {
            "model": self._gk.model,
            "messages": chat_msgs,
            "tools": to_ollama_tools(tools),
            "stream": False,
        }
        resp = httpx.post(self._gk._ollama_url, json=payload, timeout=120.0)
        resp.raise_for_status()
        return parse_ollama_response(resp.json())
