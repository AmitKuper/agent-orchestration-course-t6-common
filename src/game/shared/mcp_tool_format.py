"""Pure format-conversion helpers for LLM tool-use messages.

Converts between the unified internal representation and the wire formats
expected by Anthropic and Ollama backends.  No I/O, no state.

Unified tool definition schema follows Anthropic's convention (input_schema).
Ollama wraps each tool in {"type":"function","function":{...}} and renames
input_schema to parameters.

Result-message builders (anthropic_tool_result_messages,
ollama_tool_result_messages) live in mcp_tool_results.py and are re-exported
here so existing callers need no import changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from game.shared.mcp_tool_results import (
    anthropic_tool_result_messages,
    ollama_tool_result_messages,
)

__all__ = [
    "ToolCall", "LLMResponse",
    "to_anthropic_tools", "to_ollama_tools",
    "parse_anthropic_response", "parse_ollama_response",
    "anthropic_tool_result_messages", "ollama_tool_result_messages",
]


@dataclass
class ToolCall:
    """A single tool invocation extracted from an LLM response."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Parsed LLM response with optional tool calls."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = field(default=None, repr=False)

    @property
    def has_tool_calls(self) -> bool:
        """True if the LLM requested at least one tool call."""
        return bool(self.tool_calls)


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Return tools unchanged — unified schema matches Anthropic's wire format.

    Args:
        tools: Unified tool definitions with input_schema key.

    Returns:
        Same list (no-op conversion).
    """
    return tools


def to_ollama_tools(tools: list[dict]) -> list[dict]:
    """Convert unified tool defs to Ollama function format.

    Wraps each tool in {"type":"function","function":{...}} and renames
    input_schema → parameters.

    Args:
        tools: Unified tool definitions with input_schema key.

    Returns:
        Tool definitions suitable for the Ollama /api/chat API.
    """
    result = []
    for t in tools:
        fn = dict(t)
        fn["parameters"] = fn.pop("input_schema", {})
        result.append({"type": "function", "function": fn})
    return result


def parse_anthropic_response(response: object) -> LLMResponse:
    """Extract content and tool calls from an Anthropic messages.create response.

    Args:
        response: Raw Anthropic API response object.

    Returns:
        LLMResponse with text content and any ToolUseBlock tool calls.
    """
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:  # type: ignore[attr-defined]
        if hasattr(block, "text"):
            text_parts.append(block.text)
        elif hasattr(block, "input"):
            calls.append(ToolCall(id=block.id, name=block.name,
                                  arguments=dict(block.input)))
    return LLMResponse(content=" ".join(text_parts), tool_calls=calls, raw=response)


def parse_ollama_response(response: dict[str, object]) -> LLMResponse:
    """Extract content and tool calls from an Ollama /api/chat response dict.

    Ollama omits call IDs so uuid4 is generated for each.

    Args:
        response: Parsed JSON dict from Ollama /api/chat endpoint.

    Returns:
        LLMResponse with text content and any tool calls.
    """
    msg = response.get("message", {})
    calls: list[ToolCall] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        calls.append(ToolCall(
            id=str(uuid.uuid4()),
            name=fn.get("name", ""),
            arguments=fn.get("arguments", {}),
        ))
    return LLMResponse(content=msg.get("content", ""), tool_calls=calls, raw=response)
