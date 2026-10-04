import json
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from conversations.models import Conversation, EndUser, Message
from integrations.audio import (
    AudioTranscriptionError,
    transcribe_audio_message,
)
from integrations.transcription import get_transcription_provider
from integrations.views import (
    _extract_whatsapp_message,
    whatsapp_webhook,
)
from tenants.models import Tenant


def _tenant():
    return Tenant.objects.create(
        business_name="Audio Test Clinic",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id="audio-test-phone-id",
        whatsapp_access_token=b"audio-test-token",
    )


def _audio_payload():
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": "audio-test-phone-id",
                            },
                            "messages": [
                                {
                                    "from": "96170123456",
                                    "id": "wamid.audio-test",
                                    "type": "audio",
                                    "audio": {
                                        "id": "media-123",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_extract_audio_message_includes_media_reference():
    data = _extract_whatsapp_message(_audio_payload())

    assert data["message_type"] == "audio"
    assert data["message_content"] == ""
    assert data["media_reference"] == "media-123"


def test_disabled_transcription_backend_is_safe(settings):
    settings.TRANSCRIPTION_BACKEND = "disabled"

    with pytest.raises(ImproperlyConfigured):
        get_transcription_provider()


@pytest.mark.django_db
def test_transcribe_audio_message_persists_transcript(
    monkeypatch,
):
    tenant = _tenant()

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170123456",
    )

    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.AUDIO,
        content="",
        media_reference="media-123",
    )

    provider = Mock()
    provider.transcribe.return_value = "??? ???? ???? ????"

    monkeypatch.setattr(
        "integrations.audio.download_media",
        lambda tenant, media_reference: (
            b"fake-audio",
            "audio/ogg",
        ),
    )

    monkeypatch.setattr(
        "integrations.audio.get_transcription_provider",
        lambda: provider,
    )

    transcript = transcribe_audio_message(
        message,
        tenant,
    )

    message.refresh_from_db()

    assert transcript == "??? ???? ???? ????"
    assert message.content == transcript

    provider.transcribe.assert_called_once_with(
        audio_bytes=b"fake-audio",
        mime_type="audio/ogg",
    )


@pytest.mark.django_db
def test_audio_webhook_transcribes_before_buffering(
    monkeypatch,
    rf,
):
    _tenant()
    events = []

    monkeypatch.setattr(
        "integrations.views._has_valid_whatsapp_signature",
        lambda request: True,
    )

    def fake_transcribe(message, tenant):
        events.append("transcribed")

        assert message.media_reference == "media-123"

        message.content = "Je veux un rendez-vous demain"
        message.save(update_fields=["content"])

        return message.content

    def fake_buffer(
        tenant_id,
        end_user_id,
        message_content,
    ):
        events.append(
            (
                "buffered",
                message_content,
            )
        )

    monkeypatch.setattr(
        "integrations.views.transcribe_audio_message",
        fake_transcribe,
    )

    monkeypatch.setattr(
        "integrations.views.buffer_inbound_message",
        fake_buffer,
    )

    request = rf.post(
        "/webhooks/whatsapp/",
        data=json.dumps(_audio_payload()),
        content_type="application/json",
    )

    response = whatsapp_webhook(request)

    assert response.status_code == 200

    message = Message.objects.get(whatsapp_message_id="wamid.audio-test")

    assert message.message_type == Message.MessageType.AUDIO
    assert message.media_reference == "media-123"
    assert message.content == "Je veux un rendez-vous demain"

    assert events == [
        "transcribed",
        (
            "buffered",
            "Je veux un rendez-vous demain",
        ),
    ]


@pytest.mark.django_db
def test_audio_webhook_does_not_buffer_failed_transcription(
    monkeypatch,
    rf,
):
    _tenant()

    buffer_mock = Mock()

    monkeypatch.setattr(
        "integrations.views._has_valid_whatsapp_signature",
        lambda request: True,
    )

    monkeypatch.setattr(
        "integrations.views.transcribe_audio_message",
        Mock(side_effect=AudioTranscriptionError("transcription failed")),
    )

    monkeypatch.setattr(
        "integrations.views.buffer_inbound_message",
        buffer_mock,
    )

    request = rf.post(
        "/webhooks/whatsapp/",
        data=json.dumps(_audio_payload()),
        content_type="application/json",
    )

    response = whatsapp_webhook(request)

    assert response.status_code == 200
    buffer_mock.assert_not_called()
