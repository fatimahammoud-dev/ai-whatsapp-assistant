from types import SimpleNamespace

from integrations.agent.mock import MockAgent


def test_mock_agent_returns_plain_reply_for_regular_message():
    agent = MockAgent()
    messages = [
        SimpleNamespace(content="Hello"),
        SimpleNamespace(content="How are you?"),
    ]

    response = agent.respond(conversation=None, messages=messages)

    assert response.action == "reply"
    assert response.text == "Thanks for your message. How can I help?"
    assert response.tool is None
    assert response.tool_args == {}


def test_mock_agent_returns_check_availability_tool_call_for_booking_message():
    agent = MockAgent()
    messages = [
        SimpleNamespace(content="Hello"),
        SimpleNamespace(content="I want to book an appointment"),
    ]

    response = agent.respond(conversation=None, messages=messages)

    assert response.action == "tool_call"
    assert response.text is None
    assert response.tool == "check_availability"
    assert response.tool_args == {}
