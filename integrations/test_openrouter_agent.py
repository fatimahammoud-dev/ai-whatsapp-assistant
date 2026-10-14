from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conversations.models import Conversation, EndUser, Message
from integrations.agent.openrouter import (
    OPENROUTER_TOOLS,
    OpenRouterAgent,
)
from tenants.models import Tenant


def _conversation():
    tenant = Tenant.objects.create(
        business_name="OpenRouter Agent Test",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id="openrouter-test-phone-id",
        whatsapp_access_token=b"openrouter-test-token",
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


def _text_response(text):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=text,
                    tool_calls=None,
                )
            )
        ]
    )


def _tool_response(name, arguments):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name=name,
                                arguments=arguments,
                            )
                        )
                    ],
                )
            )
        ]
    )


@pytest.mark.django_db
def test_openrouter_agent_translates_text_response(settings):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hello",
    )

    client = Mock()
    client.chat.completions.create.return_value = _text_response(
        "Hello! How can I help?"
    )

    settings.OPENROUTER_MODEL = "test/model"
    settings.OPENROUTER_MAX_TOKENS = 256

    agent = OpenRouterAgent(client=client)

    response = agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(content="Hello"),
        ],
    )

    assert response.action == "reply"
    assert response.text == "Hello! How can I help?"
    assert response.tool is None
    assert response.tool_args == {}

    call = client.chat.completions.create.call_args.kwargs

    assert call["model"] == "test/model"
    assert call["max_tokens"] == 256
    assert call["tools"] == OPENROUTER_TOOLS

    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1:] == [
        {
            "role": "user",
            "content": "Hello",
        }
    ]


@pytest.mark.django_db
def test_openrouter_agent_translates_tool_call(settings):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="I want to book an appointment",
    )

    client = Mock()
    client.chat.completions.create.return_value = _tool_response(
        "check_availability",
        "{}",
    )

    settings.OPENROUTER_MODEL = "test/model"
    settings.OPENROUTER_MAX_TOKENS = 256

    agent = OpenRouterAgent(client=client)

    response = agent.respond(
        conversation=conversation,
        messages=[SimpleNamespace(content="I want to book an appointment")],
    )

    assert response.action == "tool_call"
    assert response.text is None
    assert response.tool == "check_availability"
    assert response.tool_args == {}


@pytest.mark.django_db
def test_openrouter_agent_builds_history_without_duplicate_buffer(
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
    client.chat.completions.create.return_value = _text_response("Sure.")

    settings.OPENROUTER_MODEL = "test/model"
    settings.OPENROUTER_MAX_TOKENS = 256

    agent = OpenRouterAgent(client=client)

    agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(
                content="I want an appointment",
            )
        ],
    )

    call = client.chat.completions.create.call_args.kwargs

    assert call["messages"][1:] == [
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
def test_openrouter_agent_sends_tenant_specific_prompt(settings):
    conversation = _conversation()

    conversation.tenant.business_name = "Maryam Medical Center"
    conversation.tenant.language_defaults = [
        "Arabic",
        "English",
    ]
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
    client.chat.completions.create.return_value = _text_response("Hello.")

    settings.OPENROUTER_MODEL = "test/model"
    settings.OPENROUTER_MAX_TOKENS = 256

    agent = OpenRouterAgent(client=client)

    agent.respond(
        conversation=conversation,
        messages=[
            SimpleNamespace(content="Hello"),
        ],
    )

    call = client.chat.completions.create.call_args.kwargs
    system_prompt = call["messages"][0]["content"]

    assert "Maryam Medical Center" in system_prompt
    assert "Arabic, English" in system_prompt
    assert "- tone: Very concise" in system_prompt
