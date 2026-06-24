"""Unit tests for game.shared.mcp_tool_format — format conversion helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from game.shared.mcp_tool_format import (
    LLMResponse,
    ToolCall,
    anthropic_tool_result_messages,
    ollama_tool_result_messages,
    parse_ollama_response,
    to_anthropic_tools,
    to_ollama_tools,
)

_SAMPLE_TOOLS = [
    {
        "name": "get_state",
        "description": "Get state.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
]


def test_to_anthropic_tools_is_identity() -> None:
    """to_anthropic_tools returns the input unchanged."""
    assert to_anthropic_tools(_SAMPLE_TOOLS) is _SAMPLE_TOOLS


def test_to_ollama_tools_wraps_in_function() -> None:
    """to_ollama_tools wraps each tool in {"type":"function","function":{...}}."""
    result = to_ollama_tools(_SAMPLE_TOOLS)
    assert result[0]["type"] == "function"
    assert "function" in result[0]


def test_to_ollama_tools_renames_input_schema() -> None:
    """to_ollama_tools renames input_schema to parameters."""
    result = to_ollama_tools(_SAMPLE_TOOLS)
    fn = result[0]["function"]
    assert "parameters" in fn
    assert "input_schema" not in fn


def test_to_ollama_tools_does_not_mutate_original() -> None:
    """to_ollama_tools does not modify the original tool list."""
    original = [dict(_SAMPLE_TOOLS[0])]
    to_ollama_tools(original)
    assert "input_schema" in original[0]


def test_parse_ollama_response_no_tool_calls() -> None:
    """parse_ollama_response returns empty tool_calls when none present."""
    raw = {"message": {"content": "Hello", "role": "assistant"}}
    resp = parse_ollama_response(raw)
    assert resp.content == "Hello"
    assert not resp.has_tool_calls


def test_parse_ollama_response_with_tool_call() -> None:
    """parse_ollama_response extracts tool calls from message.tool_calls."""
    raw = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {
                "name": "get_state", "arguments": {"game_id": "x", "actor": "cop"},
            }}],
        }
    }
    resp = parse_ollama_response(raw)
    assert resp.has_tool_calls
    assert resp.tool_calls[0].name == "get_state"
    assert resp.tool_calls[0].arguments["actor"] == "cop"


def test_parse_ollama_response_generates_id() -> None:
    """parse_ollama_response generates a UUID id for each tool call (Ollama omits them)."""
    raw = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": "take_action", "arguments": {}}}],
        }
    }
    resp = parse_ollama_response(raw)
    assert resp.tool_calls[0].id  # non-empty


def test_llm_response_has_tool_calls_property() -> None:
    """LLMResponse.has_tool_calls is True iff tool_calls is non-empty."""
    empty = LLMResponse(content="hi", tool_calls=[])
    with_calls = LLMResponse(content="", tool_calls=[ToolCall(id="1", name="x", arguments={})])
    assert not empty.has_tool_calls
    assert with_calls.has_tool_calls


def test_anthropic_tool_result_messages_structure() -> None:
    """anthropic_tool_result_messages returns [assistant_msg, user_msg_with_results]."""
    tc = ToolCall(id="abc", name="get_state", arguments={})
    msgs = anthropic_tool_result_messages([tc], ["result_text"], ["content_block"])
    assert msgs[0]["role"] == "assistant"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"][0]["type"] == "tool_result"
    assert msgs[1]["content"][0]["tool_use_id"] == "abc"


def test_ollama_tool_result_messages_structure() -> None:
    """ollama_tool_result_messages returns [assistant_msg, ...tool_msgs]."""
    tc = ToolCall(id="xyz", name="take_action", arguments={})
    msgs = ollama_tool_result_messages([tc], ["ok"], "I will move.")
    assert msgs[0]["role"] == "assistant"
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["name"] == "take_action"
    assert msgs[1]["content"] == "ok"


def test_parse_anthropic_response_text_block() -> None:
    """parse_anthropic_response extracts text from TextBlock-like objects."""
    from game.shared.mcp_tool_format import parse_anthropic_response

    text_block = MagicMock()
    text_block.text = "Moving east."
    del text_block.input  # TextBlock has no .input

    raw = MagicMock()
    raw.content = [text_block]
    resp = parse_anthropic_response(raw)
    assert "Moving east." in resp.content
    assert not resp.has_tool_calls
