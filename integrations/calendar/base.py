"""Shared calendar provider abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class TimeSlot:
    """Represent one calendar time interval."""

    start: datetime
    end: datetime


class CalendarProviderError(RuntimeError):
    """Raised when an external calendar provider operation fails."""


def token_text(value) -> str:
    """Return an encrypted-field token value as text."""
    if isinstance(value, memoryview):
        value = bytes(value)

    if isinstance(value, bytes):
        return value.decode("utf-8")

    return str(value)


def parse_datetime(value: str) -> datetime:
    """Parse an ISO/RFC3339 datetime and always return an aware value."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed


class CalendarProvider(ABC):
    """Unified interface implemented by external calendar providers."""

    refresh_leeway = timedelta(seconds=60)

    def access_token(self, connection) -> str:
        """Return a valid access token, refreshing it when needed."""
        if connection.token_expires_at <= timezone.now() + self.refresh_leeway:
            self.refresh_access_token(connection)

        return token_text(connection.access_token)

    def store_refreshed_tokens(self, connection, payload: dict) -> None:
        """Persist refreshed OAuth credentials on the connection."""
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")

        if not access_token or expires_in is None:
            raise CalendarProviderError(
                "Calendar token refresh response is missing required fields."
            )

        connection.access_token = access_token.encode("utf-8")
        connection.token_expires_at = timezone.now() + timedelta(
            seconds=int(expires_in)
        )

        update_fields = ["access_token", "token_expires_at"]

        refresh_token = payload.get("refresh_token")
        if refresh_token:
            connection.refresh_token = refresh_token.encode("utf-8")
            update_fields.append("refresh_token")

        connection.save(update_fields=update_fields)

    @abstractmethod
    def refresh_access_token(self, connection) -> None:
        """Refresh and persist the provider access token."""

    @abstractmethod
    def get_busy_intervals(self, connection, date_range) -> list[TimeSlot]:
        """Return provider busy intervals for the requested range."""

    @abstractmethod
    def create_event(self, connection, slot, summary, *, idempotency_key=None) -> str:
        """Create an external event and return its provider event ID."""
