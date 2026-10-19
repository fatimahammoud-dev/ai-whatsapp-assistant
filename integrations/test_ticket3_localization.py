from unittest.mock import Mock

import pytest

from conversations.models import Message
from integrations.agent.openrouter import OpenRouterAgent
from integrations.test_openrouter_agent import _conversation, _text_response


@pytest.mark.django_db
@pytest.mark.parametrize(
    "customer_text,formatted_reply",
    [
        (
            "بدي موعد عند الدكتور",
            "في موعد متاح بتاريخ 20 أكتوبر الساعة 10:00.",
        ),
        (
            "Je voudrais un rendez-vous",
            "Un rendez-vous est disponible le 20 octobre à 10h.",
        ),
    ],
)
def test_formatter_uses_customer_language_context(
    settings, customer_text, formatted_reply
):
    conversation = _conversation()

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content=customer_text,
    )

    client = Mock()
    client.chat.completions.create.return_value = _text_response(formatted_reply)

    settings.OPENROUTER_MODEL = "test/model"
    settings.OPENROUTER_MAX_TOKENS = 256

    agent = OpenRouterAgent(client=client)

    result = agent.format_tool_result(
        conversation=conversation,
        tool_name="check_availability",
        tool_result={
            "available_slots": [
                {
                    "start": "2026-10-20T10:00:00+03:00",
                    "end": "2026-10-20T10:30:00+03:00",
                }
            ]
        },
    )

    assert result == formatted_reply

    call = client.chat.completions.create.call_args.kwargs

    assert call["model"] == "test/model"
    assert "tools" not in call

    messages = call["messages"]

    assert customer_text in str(messages)
    assert "2026-10-20T10:00:00+03:00" in str(messages)
    assert (
        "The backend will append verified appointment slots separately."
        in messages[0]["content"]
    )
