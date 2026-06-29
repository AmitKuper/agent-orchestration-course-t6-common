"""Conversation message builders for completed tool-use rounds.

Extracted from mcp_tool_format.py to keep each module under 150 lines.
Anthropic and Ollama require different message shapes after tool execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.shared.mcp_tool_format import ToolCall


def anthropic_tool_result_messages(
    tool_calls: list[ToolCall],
    results: list[str],
    assistant_content: object,
) -> list[dict]:
    """Build Anthropic conversation messages for a completed round of tool calls.

    Anthropic requires tool results merged into a single user message with a
    content list of tool_result blocks.

    Args:
        tool_calls: Tool calls from the previous LLM response.
        results: Corresponding result strings, one per call.
        assistant_content: Raw content blocks from the assistant response.

    Returns:
        [assistant_msg, user_msg_with_tool_results]
    """
    assistant_msg = {"role": "assistant", "content": assistant_content}
    tool_results = [
        {"type": "tool_result", "tool_use_id": tc.id, "content": r}
        for tc, r in zip(tool_calls, results)
    ]
    return [assistant_msg, {"role": "user", "content": tool_results}]


def ollama_tool_result_messages(
    tool_calls: list[ToolCall],
    results: list[str],
    assistant_content: str,
) -> list[dict]:
    """Build Ollama conversation messages for a completed round of tool calls.

    Ollama accepts one tool message per result with role="tool".

    Args:
        tool_calls: Tool calls from the previous LLM response.
        results: Corresponding result strings, one per call.
        assistant_content: Text content from the assistant message.

    Returns:
        [assistant_msg, ...tool_msgs]
    """
    msgs: list[dict] = [{"role": "assistant", "content": assistant_content}]
    for tc, r in zip(tool_calls, results):
        msgs.append({"role": "tool", "name": tc.name, "content": r})
    return msgs
