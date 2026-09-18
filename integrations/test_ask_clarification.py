import pytest

from integrations.tools.clarification import ask_clarification
from integrations.tools.dispatcher import dispatch_tool


def test_ask_clarification_returns_text_unchanged():
    text = "Which day would you prefer?"

    assert ask_clarification(text) == text


def test_ask_clarification_is_wired_into_tool_dispatcher():
    text = "What time works best for you?"

    result = dispatch_tool(
        "ask_clarification",
        text=text,
    )

    assert result == text


def test_dispatch_tool_rejects_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool: missing_tool"):
        dispatch_tool("missing_tool")
