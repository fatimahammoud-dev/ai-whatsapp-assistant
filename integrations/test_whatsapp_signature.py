import hashlib
import hmac

from django.test import override_settings
from django.urls import reverse

APP_SECRET = "ticket-5-test-app-secret"


def _signature_for(body):
    digest = hmac.new(
        APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return f"sha256={digest}"


@override_settings(META_APP_SECRET=APP_SECRET)
def test_whatsapp_webhook_accepts_valid_signature(client, monkeypatch):
    body = b'{"object":"whatsapp_business_account"}'

    monkeypatch.setattr(
        "integrations.views._resolve_whatsapp_context",
        lambda payload: object(),
    )
    monkeypatch.setattr(
        "integrations.views._persist_inbound_message",
        lambda payload, resolved_context: (None, False),
    )

    response = client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_signature_for(body),
    )

    assert response.status_code == 200


@override_settings(META_APP_SECRET=APP_SECRET)
def test_whatsapp_webhook_rejects_missing_signature(client):
    body = b'{"object":"whatsapp_business_account"}'

    response = client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=body,
        content_type="application/json",
    )

    assert response.status_code == 403


@override_settings(META_APP_SECRET=APP_SECRET)
def test_whatsapp_webhook_rejects_invalid_signature(client):
    body = b'{"object":"whatsapp_business_account"}'

    response = client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
    )

    assert response.status_code == 403


@override_settings(META_APP_SECRET=APP_SECRET)
def test_whatsapp_webhook_signature_uses_raw_request_body(client):
    original_body = b'{"message":"original"}'
    tampered_body = b'{"message":"tampered"}'

    response = client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=tampered_body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_signature_for(original_body),
    )

    assert response.status_code == 403


@override_settings(META_APP_SECRET=APP_SECRET)
def test_signature_verification_happens_before_json_parsing(client, monkeypatch):
    body = b"not-valid-json"

    def fail_if_parsing_happens(*args, **kwargs):
        raise AssertionError("Payload parsing happened before signature verification")

    monkeypatch.setattr(
        "integrations.views.json.loads",
        fail_if_parsing_happens,
    )

    response = client.generic(
        "POST",
        reverse("whatsapp-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
    )

    assert response.status_code == 403
