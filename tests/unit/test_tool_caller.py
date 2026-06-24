"""Unit tests for game.shared.tool_caller — ToolCaller tool-use loop."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from game.shared.mcp_tool_format import LLMResponse, ToolCall
from game.shared.tool_caller import ToolCaller

_TOOLS = [{"name": "ping", "description": "ping",
           "input_schema": {"type": "object", "properties": {}}}]


def _make_caller(use_anthropic: bool = False) -> tuple[ToolCaller, MagicMock]:
    """Return a ToolCaller with a mock Gatekeeper."""
    gk = MagicMock()
    gk._use_anthropic = use_anthropic
    gk._enforce_rate_limit = MagicMock()
    gk.model = "test-model"
    return ToolCaller(gk), gk


def test_call_with_tools_no_tool_calls_appends_assistant() -> None:
    """When LLM returns no tool calls the final message is appended as assistant."""
    caller, _ = _make_caller()
    caller._raw_call = MagicMock(return_value=LLMResponse(content="Done!", tool_calls=[]))

    async def executor(name: str, args: dict[str, object]) -> str:
        return "unused"

    conv = asyncio.run(caller.call_with_tools(
        [{"role": "user", "content": "go"}], _TOOLS, executor
    ))
    assert conv[-1]["role"] == "assistant"
    assert conv[-1]["content"] == "Done!"


def test_call_with_tools_executes_tool_call() -> None:
    """When LLM returns a tool call the executor is invoked."""
    caller, _ = _make_caller()
    tc = ToolCall(id="1", name="ping", arguments={"x": 1})
    raw = MagicMock(content=[])
    responses = [
        LLMResponse(content="", tool_calls=[tc], raw=raw),
        LLMResponse(content="Done", tool_calls=[]),
    ]
    caller._raw_call = MagicMock(side_effect=responses)
    executed: list[tuple[str, object]] = []

    async def executor(name: str, args: dict[str, object]) -> str:
        executed.append((name, args))
        return "pong"

    asyncio.run(caller.call_with_tools(
        [{"role": "user", "content": "go"}], _TOOLS, executor
    ))
    assert executed == [("ping", {"x": 1})]


def test_call_with_tools_ollama_appends_tool_role_messages() -> None:
    """Ollama path appends role=tool messages after each tool call."""
    caller, _ = _make_caller(use_anthropic=False)
    tc = ToolCall(id="2", name="ping", arguments={})
    raw = MagicMock(content=[])
    responses = [
        LLMResponse(content="calling ping", tool_calls=[tc], raw=raw),
        LLMResponse(content="done", tool_calls=[]),
    ]
    caller._raw_call = MagicMock(side_effect=responses)

    async def executor(name: str, args: dict[str, object]) -> str:
        return "result"

    conv = asyncio.run(caller.call_with_tools(
        [{"role": "user", "content": "go"}], _TOOLS, executor
    ))
    roles = [m["role"] for m in conv]
    assert "tool" in roles


def test_call_with_tools_anthropic_appends_tool_result_messages() -> None:
    """Anthropic path appends role=user message with tool_result content list."""
    caller, _ = _make_caller(use_anthropic=True)
    tc = ToolCall(id="3", name="ping", arguments={})
    raw = MagicMock()
    raw.content = []
    responses = [
        LLMResponse(content="", tool_calls=[tc], raw=raw),
        LLMResponse(content="done", tool_calls=[]),
    ]
    caller._raw_call = MagicMock(side_effect=responses)

    async def executor(name: str, args: dict[str, object]) -> str:
        return "pong"

    conv = asyncio.run(caller.call_with_tools(
        [{"role": "user", "content": "go"}], _TOOLS, executor
    ))
    user_msgs = [m for m in conv if m["role"] == "user" and isinstance(m.get("content"), list)]
    assert user_msgs
    assert user_msgs[0]["content"][0]["type"] == "tool_result"


def test_call_with_tools_passes_system_prompt() -> None:
    """System prompt is forwarded to _raw_call."""
    caller, _ = _make_caller()
    captured: list[str | None] = []

    def fake_raw_call(
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        system: str | None,
    ) -> LLMResponse:
        captured.append(system)
        return LLMResponse(content="ok", tool_calls=[])

    caller._raw_call = fake_raw_call

    async def executor(name: str, args: dict[str, object]) -> str:
        return ""

    asyncio.run(caller.call_with_tools(
        [{"role": "user", "content": "go"}], _TOOLS, executor, system="Be a cop."
    ))
    assert captured[0] == "Be a cop."
