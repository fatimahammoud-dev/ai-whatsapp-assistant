import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse

from conversations.models import Message
from tenants.models import Tenant

APP_SECRET = "ticket-7-test-app-secret"
PHONE_NUMBER_ID = "123456789012345"
SENDER_PHONE = "96170123456"
MESSAGE_ID = "wamid.ticket-7-test-message"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        business_name="Ticket 7 Test Business",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id=PHONE_NUMBER_ID,
    )


@pytest.fixture
def text_payload():
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
                                    "wa_id": SENDER_PHONE,
                                }
                            ],
                            "messages": [
                                {
                                    "from": SENDER_PHONE,
                                    "id": MESSAGE_ID,
                                    "timestamp": "1720000000",
                                    "text": {
                                        "body": "Hello from WhatsApp",
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


def _post_payload(client, payload):
    body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    return client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_signature_for(body),
    )


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_persists_inbound_text_message(
    client,
    tenant,
    text_payload,
):
    response = _post_payload(
        client,
        text_payload,
    )

    assert response.status_code == 200

    message = Message.objects.get(
        whatsapp_message_id=MESSAGE_ID,
    )

    assert message.direction == Message.Direction.INBOUND
    assert message.message_type == Message.MessageType.TEXT
    assert message.content == "Hello from WhatsApp"
    assert message.conversation.tenant == tenant
    assert message.whatsapp_message_id == MESSAGE_ID
    assert message.raw_payload == text_payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload_type", "expected_type"),
    [
        ("audio", Message.MessageType.AUDIO),
        ("image", Message.MessageType.IMAGE),
    ],
)
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_persists_media_message_type(
    client,
    tenant,
    text_payload,
    payload_type,
    expected_type,
):
    message_data = text_payload["entry"][0]["changes"][0]["value"]["messages"][0]

    message_data.pop("text")
    message_data["type"] = payload_type
    message_data["id"] = f"wamid.ticket-7-{payload_type}"
    message_data[payload_type] = {
        "id": f"media-{payload_type}-id",
    }

    response = _post_payload(
        client,
        text_payload,
    )

    assert response.status_code == 200

    message = Message.objects.get(
        whatsapp_message_id=f"wamid.ticket-7-{payload_type}",
    )

    assert message.direction == Message.Direction.INBOUND
    assert message.message_type == expected_type
    assert message.content == ""


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_duplicate_webhook_creates_only_one_message(
    client,
    tenant,
    text_payload,
):
    first_response = _post_payload(
        client,
        text_payload,
    )
    second_response = _post_payload(
        client,
        text_payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert (
        Message.objects.filter(
            whatsapp_message_id=MESSAGE_ID,
        ).count()
        == 1
    )
