from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conversations.models import Conversation, EndUser, Message
from integrations.agent.claude import ClaudeAgent
from tenants.models import Tenant


def _conversation():
    tenant = Tenant.objects.create(
        business_name="Claude Agent Test",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id="claude-test-phone-id",
        whatsapp_access_token=b"claude-test-token",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170123456",
    )
    return Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )


@pytest.mark.django_db
def test_claude_agent_translates_text_response_to_agent_response(settings):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hello",
    )

    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text="Hello! How can I help?",
            )
        ]
    )

    settings.ANTHROPIC_MODEL = "test-model"
    settings.ANTHROPIC_MAX_TOKENS = 256

    agent = ClaudeAgent(client=client)

    response = agent.respond(
        conversation=conversation,
        messages=[SimpleNamespace(content="Hello")],
    )

    assert response.action == "reply"
    assert response.text == "Hello! How can I help?"
    assert response.tool is None
    assert response.tool_args == {}

    call = client.messages.create.call_args.kwargs

    assert call["model"] == "test-model"
    assert call["max_tokens"] == 256
    assert call["messages"] == [
        {
            "role": "user",
            "content": "Hello",
        }
    ]


@pytest.mark.django_db
def test_claude_agent_translates_tool_use_to_agent_response(settings):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="I want to book an appointment",
    )

    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="check_availability",
                input={},
            )
        ]
    )

    settings.ANTHROPIC_MODEL = "test-model"
    settings.ANTHROPIC_MAX_TOKENS = 256

    agent = ClaudeAgent(client=client)

    response = agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(
                content="I want to book an appointment",
            )
        ],
    )

    assert response.action == "tool_call"
    assert response.text is None
    assert response.tool == "check_availability"
    assert response.tool_args == {}


@pytest.mark.django_db
def test_claude_agent_builds_history_without_repeating_buffered_messages(
    settings,
):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hello",
    )
    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
        message_type=Message.MessageType.TEXT,
        content="How can I help?",
    )
    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="I want an appointment",
    )

    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text="Sure.",
            )
        ]
    )

    settings.ANTHROPIC_MODEL = "test-model"
    settings.ANTHROPIC_MAX_TOKENS = 256

    agent = ClaudeAgent(client=client)

    agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(
                content="I want an appointment",
            )
        ],
    )

    call = client.messages.create.call_args.kwargs

    assert call["messages"] == [
        {
            "role": "user",
            "content": "Hello",
        },
        {
            "role": "assistant",
            "content": "How can I help?",
        },
        {
            "role": "user",
            "content": "I want an appointment",
        },
    ]


@pytest.mark.django_db
def test_claude_agent_sends_tenant_specific_system_prompt(settings):
    conversation = _conversation()

    conversation.tenant.business_name = "Maryam Medical Center"
    conversation.tenant.language_defaults = ["Arabic", "English"]
    conversation.tenant.system_prompt_overrides = {
        "tone": "Very concise",
    }
    conversation.tenant.save(
        update_fields=[
            "business_name",
            "language_defaults",
            "system_prompt_overrides",
        ]
    )

    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text="Hello.",
            )
        ]
    )

    settings.ANTHROPIC_MODEL = "test-model"
    settings.ANTHROPIC_MAX_TOKENS = 256

    agent = ClaudeAgent(client=client)

    agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(
                content="Hello",
            )
        ],
    )

    call = client.messages.create.call_args.kwargs
    system_prompt = call["system"]

    assert "Maryam Medical Center" in system_prompt
    assert "Arabic, English" in system_prompt
    assert "- tone: Very concise" in system_prompt
