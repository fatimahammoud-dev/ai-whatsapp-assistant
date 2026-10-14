"""Transcription provider contract and configuration."""

from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class TranscriptionError(RuntimeError):
    """Raised when a configured transcription provider fails."""


class TranscriptionProvider(Protocol):
    """Contract implemented by speech-to-text providers."""

    def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str,
    ) -> str:
        """Return transcript text for one audio payload."""
        ...


def get_transcription_provider() -> TranscriptionProvider:
    """Return the configured transcription provider.

    Sprint 8 keeps the provider pluggable because the concrete paid service
    has not been approved yet.
    """
    backend = settings.TRANSCRIPTION_BACKEND

    if backend == "disabled":
        raise ImproperlyConfigured(
            "Audio transcription is disabled. "
            "Configure an approved transcription provider first."
        )

    raise ImproperlyConfigured(f"Unsupported TRANSCRIPTION_BACKEND: {backend!r}")
