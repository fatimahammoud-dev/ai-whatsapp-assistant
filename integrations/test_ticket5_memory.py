"""Regression tests for bounded and resilient conversation memory."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conversations.models import Conversation, EndUser, Message
from integrations.agent.openrouter import OpenRouterAgent
from tenants.models import Tenant


@pytest.fixture
def conversation(db):
    tenant = Tenant.objects.create(
        business_name="Memory Hardening Test",
        vertical=Tenant.Vertical.DOCTOR,
        memory_enabled=True,
        memory_max_messages=2,
        memory_summary_max_chars=150,
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170987654",
    )
    return Conversation.objects.create(tenant=tenant, end_user=end_user)


def add_message(conversation, text):
    return Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content=text,
    )


def summary_response(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


@pytest.mark.django_db
def test_long_old_message_is_truncated_for_summary(conversation):
    add_message(conversation, "X" * 100000)
    add_message(conversation, "recent one")
    add_message(conversation, "recent two")

    client = Mock()
    client.chat.completions.create.return_value = summary_response("Previous context")

    agent = OpenRouterAgent(client=client)
    agent._build_messages(conversation, [])

    call = client.chat.completions.create.call_args.kwargs
    summary_input = call["messages"][1]["content"]

    assert len(summary_input) < 15000
    assert "X" * 501 not in summary_input


@pytest.mark.django_db
def test_summary_failure_does_not_block_main_history(conversation):
    add_message(conversation, "old message")
    add_message(conversation, "recent one")
    add_message(conversation, "recent two")

    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError(
        "Temporary provider failure"
    )

    agent = OpenRouterAgent(client=client)
    history = agent._build_messages(conversation, [])

    assert "recent one" in str(history)
    assert "recent two" in str(history)

    conversation.refresh_from_db()
    assert conversation.memory_last_summarized_message_id is None


@pytest.mark.django_db
def test_summary_is_not_advanced_on_failure(conversation):
    add_message(conversation, "old message")
    add_message(conversation, "recent one")
    add_message(conversation, "recent two")

    client = Mock()
    client.chat.completions.create.side_effect = [
        RuntimeError("Temporary failure"),
        summary_response("Recovered summary"),
    ]

    agent = OpenRouterAgent(client=client)
    agent._build_messages(conversation, [])
    agent._build_messages(conversation, [])

    conversation.refresh_from_db()
    assert conversation.memory_summary == "Recovered summary"
    assert conversation.memory_last_summarized_message_id is not None
