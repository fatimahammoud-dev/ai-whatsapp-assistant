"""Verify refreshed OAuth tokens are used by calendar operations."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.utils import timezone

from integrations.calendar.base import TimeSlot
from integrations.calendar.google import (
    GOOGLE_FREE_BUSY_URL,
    GOOGLE_TOKEN_URL,
    GoogleCalendarProvider,
)
from integrations.calendar.outlook import (
    GRAPH_BASE_URL,
    OutlookCalendarProvider,
)
from tenants.models import Tenant


class FakeConnection:
    def __init__(self, provider):
        self.provider = provider
        self.access_token = b"expired-access-token"
        self.refresh_token = b"refresh-token"
        self.token_expires_at = timezone.now() - timedelta(minutes=5)
        self.external_calendar_id = "test-calendar"
        self.scopes = ["Calendars.ReadWrite", "offline_access"]
        self.tenant = SimpleNamespace(timezone="Asia/Beirut")
        self.saved_update_fields = None

    def save(self, *, update_fields):
        self.saved_update_fields = update_fields


@pytest.fixture
def slot():
    return TimeSlot(
        start=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
        end=datetime(2026, 10, 20, 9, 30, tzinfo=UTC),
    )


@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="google-client",
    GOOGLE_CALENDAR_CLIENT_SECRET="google-secret",
)
@pytest.mark.parametrize("operation", ["availability", "create_event"])
def test_google_refreshes_before_calendar_operation(monkeypatch, slot, operation):
    connection = FakeConnection(Tenant.CalendarProvider.GOOGLE)
    provider = GoogleCalendarProvider()
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))

        if url == GOOGLE_TOKEN_URL:
            return {
                "access_token": "new-google-token",
                "expires_in": 3600,
            }

        assert kwargs["access_token"] == "new-google-token"

        if url == GOOGLE_FREE_BUSY_URL:
            return {"calendars": {connection.external_calendar_id: {"busy": []}}}

        return {"id": "google-event-123"}

    monkeypatch.setattr(
        "integrations.calendar.google.request_json",
        fake_request_json,
    )

    if operation == "availability":
        assert provider.get_busy_intervals(connection, slot) == []
    else:
        assert (
            provider.create_event(connection, slot, "Consultation")
            == "google-event-123"
        )

    assert len(calls) == 2
    assert calls[0][0] == GOOGLE_TOKEN_URL
    assert calls[1][1]["access_token"] == "new-google-token"
    assert connection.access_token == b"new-google-token"
    assert connection.token_expires_at > timezone.now()
    assert connection.saved_update_fields == [
        "access_token",
        "token_expires_at",
    ]


@override_settings(
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-client",
    MICROSOFT_CALENDAR_CLIENT_SECRET="microsoft-secret",
    MICROSOFT_CALENDAR_TENANT="common",
)
@pytest.mark.parametrize("operation", ["availability", "create_event"])
def test_outlook_refreshes_before_calendar_operation(monkeypatch, slot, operation):
    connection = FakeConnection(Tenant.CalendarProvider.OUTLOOK)
    provider = OutlookCalendarProvider()
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))

        if "/oauth2/v2.0/token" in url:
            return {
                "access_token": "new-outlook-token",
                "refresh_token": "new-outlook-refresh",
                "expires_in": 3600,
            }

        assert url.startswith(GRAPH_BASE_URL)
        assert kwargs["access_token"] == "new-outlook-token"

        if operation == "availability":
            return {"value": []}

        return {"id": "outlook-event-456"}

    monkeypatch.setattr(
        "integrations.calendar.outlook.request_json",
        fake_request_json,
    )

    if operation == "availability":
        assert provider.get_busy_intervals(connection, slot) == []
    else:
        assert (
            provider.create_event(connection, slot, "Consultation")
            == "outlook-event-456"
        )

    assert len(calls) == 2
    assert "/oauth2/v2.0/token" in calls[0][0]
    assert calls[1][1]["access_token"] == "new-outlook-token"
    assert connection.access_token == b"new-outlook-token"
    assert connection.refresh_token == b"new-outlook-refresh"
    assert connection.token_expires_at > timezone.now()
    assert connection.saved_update_fields == [
        "access_token",
        "token_expires_at",
        "refresh_token",
    ]
