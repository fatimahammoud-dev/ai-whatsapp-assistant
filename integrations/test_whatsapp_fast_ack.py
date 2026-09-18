import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse

from conversations.models import Message
from tenants.models import Tenant

APP_SECRET = "ticket-8-test-app-secret"
PHONE_NUMBER_ID = "123456789012345"
MESSAGE_ID = "wamid.ticket-8-fast-ack"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        business_name="Ticket 8 Test Business",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id=PHONE_NUMBER_ID,
    )


@pytest.fixture
def inbound_payload():
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test-waba-id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Test User",
                                    },
                                    "wa_id": "96170123456",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "96170123456",
                                    "id": MESSAGE_ID,
                                    "timestamp": "1720000000",
                                    "text": {
                                        "body": "Hello from Ticket 8",
                                    },
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _signature_for(body):
    digest = hmac.new(
        APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return f"sha256={digest}"


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_persists_message_buffers_processing_and_returns_200(
    client,
    tenant,
    inbound_payload,
):
    body = json.dumps(
        inbound_payload,
        separators=(",", ":"),
    ).encode("utf-8")

    with patch("integrations.views.buffer_inbound_message") as buffer_mock:
        response = client.generic(
            "POST",
            reverse("whatsapp-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=_signature_for(body),
        )

    assert response.status_code == 200

    message = Message.objects.get(
        whatsapp_message_id=MESSAGE_ID,
    )

    assert message.conversation.tenant == tenant
    assert message.direction == Message.Direction.INBOUND
    assert message.content == "Hello from Ticket 8"

    buffer_mock.assert_called_once_with(
        tenant.pk,
        message.conversation.end_user_id,
        "Hello from Ticket 8",
    )
