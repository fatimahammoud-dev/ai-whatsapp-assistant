"""Inbound WhatsApp audio processing."""

from django.core.exceptions import ImproperlyConfigured

from conversations.models import Message
from integrations.transcription import (
    TranscriptionError,
    get_transcription_provider,
)
from integrations.whatsapp import (
    WhatsAppMediaDownloadError,
    download_media,
)


class AudioTranscriptionError(RuntimeError):
    """Raised when an inbound audio message cannot be transcribed."""


def transcribe_audio_message(message, tenant):
    """Download, transcribe, and persist one inbound audio message."""
    if message.message_type != Message.MessageType.AUDIO:
        raise AudioTranscriptionError("Only audio messages can be transcribed.")

    if not message.media_reference:
        raise AudioTranscriptionError("Audio message has no media reference.")

    try:
        audio_bytes, mime_type = download_media(
            tenant,
            message.media_reference,
        )

        provider = get_transcription_provider()

        transcript = provider.transcribe(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
        )

    except (
        WhatsAppMediaDownloadError,
        TranscriptionError,
        ImproperlyConfigured,
    ) as exc:
        raise AudioTranscriptionError("Inbound audio transcription failed.") from exc

    transcript = transcript.strip()

    if not transcript:
        raise AudioTranscriptionError(
            "Transcription provider returned an empty transcript."
        )

    message.content = transcript
    message.save(update_fields=["content"])

    return transcript
