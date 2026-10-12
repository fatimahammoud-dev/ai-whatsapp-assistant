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
        message.pk,
    )


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_audio_with_empty_content_is_buffered_by_message_id(
    client,
    tenant,
    inbound_payload,
):
    payload = json.loads(json.dumps(inbound_payload))
    message_data = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message_data["id"] = "wamid.ticket-8-audio"
    message_data["type"] = "audio"
    message_data.pop("text", None)

    body = json.dumps(payload).encode("utf-8")

    with patch("integrations.views.buffer_inbound_message") as buffer_mock:
        response = client.generic(
            "POST",
            reverse("whatsapp-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=_signature_for(body),
        )

    assert response.status_code == 200

    saved = Message.objects.get(
        whatsapp_message_id="wamid.ticket-8-audio",
    )
    assert saved.content == ""

    buffer_mock.assert_called_once_with(
        tenant.pk,
        saved.conversation.end_user_id,
        saved.pk,
    )


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_buffer_failure_rolls_back_message_and_retry_succeeds(
    client,
    tenant,
    inbound_payload,
):
    body = json.dumps(inbound_payload).encode("utf-8")
    signature = _signature_for(body)

    client.raise_request_exception = False

    with patch(
        "integrations.views.buffer_inbound_message",
        side_effect=ConnectionError("Redis unavailable"),
    ) as failed_buffer:
        failed_response = client.generic(
            "POST",
            reverse("whatsapp-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    assert failed_response.status_code == 500
    failed_buffer.assert_called_once()

    assert not Message.objects.filter(
        whatsapp_message_id=MESSAGE_ID,
    ).exists()

    with patch("integrations.views.buffer_inbound_message") as retry_buffer:
        retry_response = client.generic(
            "POST",
            reverse("whatsapp-webhook"),
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    assert retry_response.status_code == 200

    saved_message = Message.objects.get(
        whatsapp_message_id=MESSAGE_ID,
    )

    retry_buffer.assert_called_once_with(
        tenant.pk,
        saved_message.conversation.end_user_id,
        saved_message.pk,
    )
