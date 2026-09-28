from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from django.test import override_settings
from django.utils import timezone

from integrations.calendar.base import TimeSlot
from integrations.calendar.google import GoogleCalendarProvider
from integrations.calendar.outlook import OutlookCalendarProvider
from integrations.calendar.registry import get_calendar_provider
from tenants.models import Tenant


class FakeConnection:
    def __init__(
        self,
        *,
        provider=Tenant.CalendarProvider.GOOGLE,
        access_token=b"access-token",
        refresh_token=b"refresh-token",
        token_expires_at=None,
        external_calendar_id="calendar@example.com",
        scopes=None,
    ):
        self.provider = provider
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at or (
            timezone.now() + timedelta(hours=1)
        )
        self.external_calendar_id = external_calendar_id
        self.scopes = scopes or []
        self.tenant = SimpleNamespace(timezone="Asia/Beirut")
        self.saved_update_fields = None

    def save(self, *, update_fields):
        self.saved_update_fields = update_fields


def test_calendar_registry_returns_google_and_outlook_providers():
    google = FakeConnection(provider=Tenant.CalendarProvider.GOOGLE)
    outlook = FakeConnection(provider=Tenant.CalendarProvider.OUTLOOK)

    assert isinstance(
        get_calendar_provider(google),
        GoogleCalendarProvider,
    )
    assert isinstance(
        get_calendar_provider(outlook),
        OutlookCalendarProvider,
    )


def test_google_returns_busy_intervals(monkeypatch):
    connection = FakeConnection()
    provider = GoogleCalendarProvider()

    date_range = TimeSlot(
        start=datetime(2026, 10, 1, 6, 0, tzinfo=UTC),
        end=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )

    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        return {
            "calendars": {
                connection.external_calendar_id: {
                    "busy": [
                        {
                            "start": "2026-10-01T07:00:00Z",
                            "end": "2026-10-01T08:00:00Z",
                        },
                        {
                            "start": "2026-10-01T10:00:00Z",
                            "end": "2026-10-01T10:30:00Z",
                        },
                    ]
                }
            }
        }

    monkeypatch.setattr(
        "integrations.calendar.google.request_json",
        fake_request_json,
    )

    intervals = provider.get_busy_intervals(
        connection,
        date_range,
    )

    assert intervals == [
        TimeSlot(
            start=datetime(2026, 10, 1, 7, 0, tzinfo=UTC),
            end=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
        ),
        TimeSlot(
            start=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            end=datetime(2026, 10, 1, 10, 30, tzinfo=UTC),
        ),
    ]

    assert captured["method"] == "POST"
    assert captured["access_token"] == "access-token"
    assert captured["payload"]["items"] == [{"id": connection.external_calendar_id}]


def test_google_creates_event_and_returns_external_id(monkeypatch):
    connection = FakeConnection()
    provider = GoogleCalendarProvider()

    slot = TimeSlot(
        start=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        end=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),
    )

    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return {"id": "google-event-123"}

    monkeypatch.setattr(
        "integrations.calendar.google.request_json",
        fake_request_json,
    )

    event_id = provider.create_event(
        connection,
        slot,
        "Consultation",
    )

    assert event_id == "google-event-123"
    assert captured["method"] == "POST"
    assert captured["payload"]["summary"] == "Consultation"


@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="google-client",
    GOOGLE_CALENDAR_CLIENT_SECRET="google-secret",
)
def test_google_refreshes_expired_access_token(monkeypatch):
    connection = FakeConnection(
        token_expires_at=timezone.now() - timedelta(minutes=1),
    )
    provider = GoogleCalendarProvider()

    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        return {
            "access_token": "new-google-access-token",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        "integrations.calendar.google.request_json",
        fake_request_json,
    )

    token = provider.access_token(connection)

    assert token == "new-google-access-token"
    assert connection.access_token == b"new-google-access-token"
    assert connection.saved_update_fields == [
        "access_token",
        "token_expires_at",
    ]

    assert captured["form"]["refresh_token"] == "refresh-token"
    assert captured["form"]["grant_type"] == "refresh_token"


def test_outlook_returns_busy_intervals_and_ignores_free_events(monkeypatch):
    connection = FakeConnection(
        provider=Tenant.CalendarProvider.OUTLOOK,
        external_calendar_id="outlook-calendar",
    )
    provider = OutlookCalendarProvider()

    date_range = TimeSlot(
        start=datetime(2026, 10, 1, 6, 0, tzinfo=UTC),
        end=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )

    responses = [
        {
            "value": [
                {
                    "start": {"dateTime": "2026-10-01T07:00:00"},
                    "end": {"dateTime": "2026-10-01T08:00:00"},
                    "showAs": "busy",
                    "isCancelled": False,
                },
                {
                    "start": {"dateTime": "2026-10-01T08:00:00"},
                    "end": {"dateTime": "2026-10-01T09:00:00"},
                    "showAs": "free",
                    "isCancelled": False,
                },
                {
                    "start": {"dateTime": "2026-10-01T09:00:00"},
                    "end": {"dateTime": "2026-10-01T10:00:00"},
                    "showAs": "busy",
                    "isCancelled": True,
                },
            ],
            "@odata.nextLink": "https://graph.microsoft.com/next-page",
        },
        {
            "value": [
                {
                    "start": {"dateTime": "2026-10-01T10:00:00"},
                    "end": {"dateTime": "2026-10-01T10:30:00"},
                    "showAs": "tentative",
                    "isCancelled": False,
                }
            ]
        },
    ]

    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(
        "integrations.calendar.outlook.request_json",
        fake_request_json,
    )

    intervals = provider.get_busy_intervals(
        connection,
        date_range,
    )

    assert intervals == [
        TimeSlot(
            start=datetime(2026, 10, 1, 7, 0, tzinfo=UTC),
            end=datetime(2026, 10, 1, 8, 0, tzinfo=UTC),
        ),
        TimeSlot(
            start=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            end=datetime(2026, 10, 1, 10, 30, tzinfo=UTC),
        ),
    ]

    assert len(calls) == 2
    assert calls[0][1]["access_token"] == "access-token"


def test_outlook_creates_event_and_returns_external_id(monkeypatch):
    connection = FakeConnection(
        provider=Tenant.CalendarProvider.OUTLOOK,
        external_calendar_id="outlook-calendar",
    )
    provider = OutlookCalendarProvider()

    slot = TimeSlot(
        start=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        end=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),
    )

    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return {"id": "outlook-event-456"}

    monkeypatch.setattr(
        "integrations.calendar.outlook.request_json",
        fake_request_json,
    )

    event_id = provider.create_event(
        connection,
        slot,
        "Consultation",
    )

    assert event_id == "outlook-event-456"
    assert captured["method"] == "POST"
    assert captured["payload"]["subject"] == "Consultation"
    assert captured["payload"]["start"]["timeZone"] == "UTC"
    assert captured["payload"]["end"]["timeZone"] == "UTC"


@override_settings(
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-client",
    MICROSOFT_CALENDAR_CLIENT_SECRET="microsoft-secret",
    MICROSOFT_CALENDAR_TENANT="common",
)
def test_outlook_refreshes_expired_access_token(monkeypatch):
    connection = FakeConnection(
        provider=Tenant.CalendarProvider.OUTLOOK,
        token_expires_at=timezone.now() - timedelta(minutes=1),
        scopes=["offline_access", "Calendars.ReadWrite"],
    )
    provider = OutlookCalendarProvider()

    captured = {}

    def fake_request_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)

        return {
            "access_token": "new-outlook-access-token",
            "refresh_token": "new-outlook-refresh-token",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        "integrations.calendar.outlook.request_json",
        fake_request_json,
    )

    token = provider.access_token(connection)

    assert token == "new-outlook-access-token"
    assert connection.access_token == b"new-outlook-access-token"
    assert connection.refresh_token == b"new-outlook-refresh-token"

    assert connection.saved_update_fields == [
        "access_token",
        "token_expires_at",
        "refresh_token",
    ]

    assert captured["form"]["scope"] == ("offline_access Calendars.ReadWrite")
    assert captured["form"]["grant_type"] == "refresh_token"
