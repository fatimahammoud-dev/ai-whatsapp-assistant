from types import SimpleNamespace
from unittest.mock import Mock

from integrations.agent.base import AgentResponse
from integrations.tasks import process_buffered_messages


def _fake_conversation():
    return SimpleNamespace(
        pk=303,
        tenant_id=101,
        end_user_id=202,
        status="active",
        tenant=SimpleNamespace(pk=101),
        end_user=SimpleNamespace(
            pk=202,
            phone_number="96170123456",
        ),
    )


def _message(conversation, content):
    return SimpleNamespace(
        content=content,
        conversation=conversation,
        conversation_id=conversation.pk,
    )


def _mock_conversation_query(monkeypatch, conversation):
    queryset = Mock()
    queryset.filter.return_value = queryset
    queryset.order_by.return_value = queryset
    queryset.first.return_value = conversation

    manager = Mock()
    manager.select_related.return_value = queryset

    monkeypatch.setattr(
        "integrations.tasks.Conversation.objects",
        manager,
    )


def test_process_buffered_messages_sends_plain_agent_reply(monkeypatch):
    conversation = _fake_conversation()
    _mock_conversation_query(monkeypatch, conversation)

    respond_mock = Mock(
        return_value=AgentResponse(
            action="reply",
            text="Thanks for your message. How can I help?",
        )
    )
    send_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.MockAgent.respond",
        respond_mock,
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    process_buffered_messages(
        tenant_id=101,
        end_user_id=202,
        messages=[
            _message(conversation, "Hello"),
            _message(conversation, "How are you?"),
        ],
    )

    respond_mock.assert_called_once()

    _, kwargs = respond_mock.call_args
    assert kwargs["conversation"] is conversation
    assert [message.content for message in kwargs["messages"]] == [
        "Hello",
        "How are you?",
    ]

    send_mock.assert_called_once_with(
        conversation,
        "Thanks for your message. How can I help?",
    )


def test_process_buffered_messages_recognizes_tool_call(monkeypatch):
    conversation = _fake_conversation()
    _mock_conversation_query(monkeypatch, conversation)

    respond_mock = Mock(
        return_value=AgentResponse(
            action="tool_call",
            tool="check_availability",
            tool_args={},
        )
    )
    send_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.MockAgent.respond",
        respond_mock,
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    process_buffered_messages(
        tenant_id=101,
        end_user_id=202,
        messages=[_message(conversation, "I want to book an appointment")],
    )

    respond_mock.assert_called_once()

    send_mock.assert_called_once_with(
        conversation,
        "Available appointment times: "
        "2026-01-15 09:00, "
        "2026-01-15 11:00, "
        "2026-01-15 14:00",
    )


def test_process_buffered_messages_stops_without_active_conversation(
    monkeypatch,
):
    _mock_conversation_query(monkeypatch, None)

    respond_mock = Mock()
    send_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.MockAgent.respond",
        respond_mock,
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    process_buffered_messages(
        tenant_id=101,
        end_user_id=202,
        messages=[],
    )

    respond_mock.assert_not_called()
    send_mock.assert_not_called()


def test_multiline_message_preserves_original_object(monkeypatch):
    conversation = _fake_conversation()
    _mock_conversation_query(monkeypatch, conversation)

    original = SimpleNamespace(
        content="Hello\nI need an appointment",
        pk=777,
        message_type="text",
        conversation=conversation,
        conversation_id=conversation.pk,
    )

    respond_mock = Mock(return_value=AgentResponse(action="reply", text="Hello"))
    send_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.MockAgent.respond",
        respond_mock,
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    process_buffered_messages(
        tenant_id=101,
        end_user_id=202,
        messages=[original],
    )

    actual_messages = respond_mock.call_args.kwargs["messages"]
    assert len(actual_messages) == 1
    assert actual_messages[0] is original
    assert actual_messages[0].content == "Hello\nI need an appointment"
    assert actual_messages[0].pk == 777
    send_mock.assert_called_once_with(conversation, "Hello")
