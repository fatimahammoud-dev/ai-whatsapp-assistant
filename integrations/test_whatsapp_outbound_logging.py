import logging
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from conversations.models import Conversation, EndUser, Message
from integrations.whatsapp import (
    GRAPH_API_VERSION,
    send_text_message,
)
from tenants.models import Tenant

PHONE_NUMBER_ID = "123456789012345"
ACCESS_TOKEN = b"tenant-specific-access-token"
RECIPIENT = "96170123456"


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def tenant(db):
    tenant = Tenant.objects.create(
        business_name="Outbound Logging Test Business",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id=PHONE_NUMBER_ID,
        whatsapp_access_token=ACCESS_TOKEN,
    )

    tenant.refresh_from_db()

    return tenant


@pytest.fixture
def conversation(tenant):
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number=RECIPIENT,
    )

    return Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )


@pytest.mark.django_db
def test_successful_send_logs_outbound_message_in_conversation_order(
    tenant,
    conversation,
):
    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hello",
        whatsapp_message_id="wamid.ticket-5-inbound",
    )

    with patch(
        "integrations.whatsapp.urlopen",
        return_value=FakeResponse(200),
    ):
        result = send_text_message(
            tenant,
            RECIPIENT,
            "Hello, how can I help?",
        )

    assert result is True

    messages = list(
        Message.objects.filter(
            conversation=conversation,
        )
    )

    assert len(messages) == 2

    assert messages[0].direction == Message.Direction.INBOUND
    assert messages[0].content == "Hello"

    assert messages[1].direction == Message.Direction.OUTBOUND
    assert messages[1].message_type == Message.MessageType.TEXT
    assert messages[1].content == "Hello, how can I help?"


@pytest.mark.django_db
def test_failed_send_is_not_logged_as_outbound_message(
    tenant,
    conversation,
    caplog,
):
    api_error = HTTPError(
        url=(
            f"https://graph.facebook.com/"
            f"{GRAPH_API_VERSION}/"
            f"{PHONE_NUMBER_ID}/messages"
        ),
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=None,
    )

    with patch(
        "integrations.whatsapp.urlopen",
        side_effect=api_error,
    ):
        with caplog.at_level(
            logging.ERROR,
            logger="integrations.whatsapp",
        ):
            result = send_text_message(
                tenant,
                RECIPIENT,
                "This message should not be logged",
            )

    assert result is False

    assert (
        Message.objects.filter(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
        ).count()
        == 0
    )

    assert "status=400" in caplog.text
