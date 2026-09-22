import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse

from conversations.models import Conversation, EndUser
from integrations.views import _extract_whatsapp_message
from tenants.models import Tenant

APP_SECRET = "ticket-6-test-app-secret"
PHONE_NUMBER_ID = "123456789012345"
SENDER_PHONE = "96170123456"


@pytest.fixture
def sample_meta_webhook_payload():
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
                                    "id": "wamid.test-message",
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


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        business_name="Ticket 6 Test Business",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id=PHONE_NUMBER_ID,
    )


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


def test_extracts_phone_number_sender_and_message_content(
    sample_meta_webhook_payload,
):
    message_data = _extract_whatsapp_message(
        sample_meta_webhook_payload,
    )

    assert message_data["phone_number_id"] == PHONE_NUMBER_ID
    assert message_data["sender_phone_number"] == SENDER_PHONE
    assert message_data["message_content"] == "Hello from WhatsApp"


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_resolves_tenant_and_creates_end_user_and_conversation(
    client,
    tenant,
    sample_meta_webhook_payload,
):
    response = _post_payload(
        client,
        sample_meta_webhook_payload,
    )

    assert response.status_code == 200

    end_user = EndUser.objects.get(
        tenant=tenant,
        phone_number=SENDER_PHONE,
    )

    conversation = Conversation.objects.get(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    assert conversation.tenant == tenant
    assert conversation.end_user == end_user


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_reuses_existing_active_conversation(
    client,
    tenant,
    sample_meta_webhook_payload,
):
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number=SENDER_PHONE,
    )

    existing_conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    response = _post_payload(
        client,
        sample_meta_webhook_payload,
    )

    assert response.status_code == 200

    active_conversations = Conversation.objects.filter(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    assert active_conversations.count() == 1
    assert active_conversations.get().pk == existing_conversation.pk


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_webhook_creates_active_conversation_if_only_closed_one_exists(
    client,
    tenant,
    sample_meta_webhook_payload,
):
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number=SENDER_PHONE,
    )

    Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.CLOSED,
    )

    response = _post_payload(
        client,
        sample_meta_webhook_payload,
    )

    assert response.status_code == 200

    assert (
        Conversation.objects.filter(
            tenant=tenant,
            end_user=end_user,
            status=Conversation.Status.ACTIVE,
        ).count()
        == 1
    )


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_end_user_is_scoped_to_resolved_tenant(
    client,
    tenant,
    sample_meta_webhook_payload,
):
    other_tenant = Tenant.objects.create(
        business_name="Other Business",
        vertical=Tenant.Vertical.LAWYER,
        phone_number_id="999999999999999",
    )

    EndUser.objects.create(
        tenant=other_tenant,
        phone_number=SENDER_PHONE,
    )

    response = _post_payload(
        client,
        sample_meta_webhook_payload,
    )

    assert response.status_code == 200

    assert (
        EndUser.objects.filter(
            tenant=tenant,
            phone_number=SENDER_PHONE,
        ).count()
        == 1
    )

    assert (
        EndUser.objects.filter(
            tenant=other_tenant,
            phone_number=SENDER_PHONE,
        ).count()
        == 1
    )


@pytest.mark.django_db
@override_settings(META_APP_SECRET=APP_SECRET)
def test_unknown_phone_number_id_returns_404_and_is_logged(
    client,
    sample_meta_webhook_payload,
    caplog,
):
    response = _post_payload(
        client,
        sample_meta_webhook_payload,
    )

    assert response.status_code == 404
    assert EndUser.objects.count() == 0
    assert Conversation.objects.count() == 0

    assert PHONE_NUMBER_ID in caplog.text
