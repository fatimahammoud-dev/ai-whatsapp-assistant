from django.test import override_settings
from django.urls import reverse


@override_settings(WHATSAPP_VERIFY_TOKEN="ticket-4-test-token")
def test_whatsapp_webhook_verification_succeeds(client):
    response = client.get(
        reverse("whatsapp-webhook"),
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "ticket-4-test-token",
            "hub.challenge": "123456789",
        },
    )

    assert response.status_code == 200
    assert response.content == b"123456789"
    assert response["Content-Type"].startswith("text/plain")


@override_settings(WHATSAPP_VERIFY_TOKEN="ticket-4-test-token")
def test_whatsapp_webhook_rejects_wrong_token(client):
    response = client.get(
        reverse("whatsapp-webhook"),
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "123456789",
        },
    )

    assert response.status_code == 403


@override_settings(WHATSAPP_VERIFY_TOKEN="ticket-4-test-token")
def test_whatsapp_webhook_rejects_wrong_mode(client):
    response = client.get(
        reverse("whatsapp-webhook"),
        {
            "hub.mode": "invalid",
            "hub.verify_token": "ticket-4-test-token",
            "hub.challenge": "123456789",
        },
    )

    assert response.status_code == 403


@override_settings(WHATSAPP_VERIFY_TOKEN="ticket-4-test-token")
def test_whatsapp_webhook_rejects_missing_parameters(client):
    response = client.get(reverse("whatsapp-webhook"))

    assert response.status_code == 403
