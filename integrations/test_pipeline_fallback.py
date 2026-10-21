from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from integrations import tasks


def _conversation():
    return SimpleNamespace(
        pk=303,
        tenant_id=101,
        end_user_id=202,
        status="active",
        tenant=object(),
        end_user=object(),
    )


def _message(conversation):
    return SimpleNamespace(
        conversation=conversation,
        conversation_id=conversation.pk,
        content="I want an appointment",
    )


@pytest.mark.parametrize("failure_source", ["agent", "tool"])
def test_processing_failure_sends_fallback(monkeypatch, failure_source):
    conversation = _conversation()
    message = _message(conversation)
    send = Mock()

    monkeypatch.setattr(tasks, "send_text_message", send)

    if failure_source == "agent":
        agent = Mock()
        agent.respond.side_effect = RuntimeError("agent failed")
        monkeypatch.setattr(tasks, "MockAgent", Mock(return_value=agent))
    else:
        agent = Mock()
        agent.respond.return_value = SimpleNamespace(
            action="tool_call",
            tool="check_availability",
            tool_args={},
        )
        monkeypatch.setattr(tasks, "MockAgent", Mock(return_value=agent))
        tool = Mock(side_effect=RuntimeError("tool failed"))
        monkeypatch.setattr(tasks, "run_tool", tool)

    tasks.process_buffered_messages(101, 202, [message])

    send.assert_called_once_with(conversation, tasks.FALLBACK_REPLY)


@pytest.mark.parametrize("action", ["unknown", None])
def test_unknown_agent_action_sends_fallback(monkeypatch, action):
    conversation = _conversation()
    message = _message(conversation)
    agent = Mock()
    agent.respond.return_value = SimpleNamespace(action=action)
    send = Mock()

    monkeypatch.setattr(tasks, "MockAgent", Mock(return_value=agent))
    monkeypatch.setattr(tasks, "send_text_message", send)

    tasks.process_buffered_messages(101, 202, [message])

    send.assert_called_once_with(conversation, tasks.FALLBACK_REPLY)


def test_unknown_tool_sends_fallback(monkeypatch):
    conversation = _conversation()
    message = _message(conversation)
    agent = Mock()
    agent.respond.return_value = SimpleNamespace(
        action="tool_call",
        tool="unknown_tool",
        tool_args={},
    )
    send = Mock()

    monkeypatch.setattr(tasks, "MockAgent", Mock(return_value=agent))
    monkeypatch.setattr(tasks, "send_text_message", send)

    tasks.process_buffered_messages(101, 202, [message])

    send.assert_called_once_with(conversation, tasks.FALLBACK_REPLY)
