"""Ticket 4 calendar retry and idempotency tests."""

import io
from datetime import UTC, datetime
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from integrations.calendar.base import CalendarProviderError, TimeSlot
from integrations.calendar.google import GoogleCalendarProvider
from integrations.calendar.http import request_json
from integrations.calendar.outlook import OutlookCalendarProvider


def test_calendar_http_retries_transient_get():
    response = type(
        "Response",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self: b'{"ok": true}',
        },
    )()

    error = HTTPError(
        "https://example.com",
        503,
        "Unavailable",
        {},
        io.BytesIO(b""),
    )

    with (
        patch(
            "integrations.calendar.http.urlopen",
            side_effect=[error, response],
        ) as mocked,
        patch("integrations.retry.time.sleep"),
    ):
        assert request_json("https://example.com") == {"ok": True}

    assert mocked.call_count == 2


def test_calendar_http_does_not_retry_unsafe_post():
    error = HTTPError(
        "https://example.com",
        503,
        "Unavailable",
        {},
        io.BytesIO(b""),
    )

    with patch(
        "integrations.calendar.http.urlopen",
        side_effect=error,
    ) as mocked:
        with pytest.raises(CalendarProviderError):
            request_json(
                "https://example.com",
                method="POST",
                payload={"event": "test"},
            )

    assert mocked.call_count == 1


def test_calendar_http_does_not_retry_permanent_error():
    error = HTTPError(
        "https://example.com",
        401,
        "Unauthorized",
        {},
        io.BytesIO(b""),
    )

    with patch(
        "integrations.calendar.http.urlopen",
        side_effect=error,
    ) as mocked:
        with pytest.raises(CalendarProviderError):
            request_json("https://example.com")

    assert mocked.call_count == 1


def test_google_idempotency_key_stable():
    provider = GoogleCalendarProvider()
    slot = TimeSlot(
        start=datetime(2026, 10, 20, 10, tzinfo=UTC),
        end=datetime(2026, 10, 20, 11, tzinfo=UTC),
    )

    class Connection:
        external_calendar_id = "primary"

    connection = Connection()

    with (
        patch.object(provider, "access_token", return_value="token"),
        patch(
            "integrations.calendar.google.request_json",
            return_value={"id": "google-event"},
        ) as mocked,
    ):
        provider.create_event(
            connection,
            slot,
            "Appointment",
            idempotency_key="booking-42",
        )
        provider.create_event(
            connection,
            slot,
            "Appointment",
            idempotency_key="booking-42",
        )

    first = mocked.call_args_list[0].kwargs["payload"]["id"]
    second = mocked.call_args_list[1].kwargs["payload"]["id"]
    assert first == second
    assert mocked.call_args_list[0].kwargs["retry_safe"] is True


def test_outlook_uses_stable_transaction_id():
    provider = OutlookCalendarProvider()
    slot = TimeSlot(
        start=datetime(2026, 10, 20, 10, tzinfo=UTC),
        end=datetime(2026, 10, 20, 11, tzinfo=UTC),
    )

    class Connection:
        external_calendar_id = "primary"

    with (
        patch.object(provider, "access_token", return_value="token"),
        patch(
            "integrations.calendar.outlook.request_json",
            return_value={"id": "outlook-event"},
        ) as mocked,
    ):
        provider.create_event(
            Connection(),
            slot,
            "Appointment",
            idempotency_key="booking-42",
        )

    assert mocked.call_args.kwargs["payload"]["transactionId"] == "booking-42"
    assert mocked.call_args.kwargs["retry_safe"] is True


def test_google_recovers_matching_409():
    import hashlib

    provider = GoogleCalendarProvider()
    slot = TimeSlot(
        start=datetime(2026, 10, 20, 10, tzinfo=UTC),
        end=datetime(2026, 10, 20, 11, tzinfo=UTC),
    )

    class Connection:
        external_calendar_id = "primary"

    expected_id = hashlib.sha256(b"booking-42").hexdigest()[:32]
    conflict = HTTPError(
        "https://example.com",
        409,
        "Conflict",
        {},
        io.BytesIO(b""),
    )

    existing = {
        "id": expected_id,
        "summary": "Appointment",
        "start": {"dateTime": slot.start.isoformat()},
        "end": {"dateTime": slot.end.isoformat()},
    }

    with (
        patch.object(provider, "access_token", return_value="token"),
        patch(
            "integrations.calendar.google.request_json",
            side_effect=[
                CalendarProviderError("Conflict"),
                existing,
            ],
        ) as mocked,
    ):
        # Preserve the HTTP cause used by the provider's conflict detection.
        mocked.side_effect = [
            _calendar_conflict(conflict),
            existing,
        ]
        assert (
            provider.create_event(
                Connection(),
                slot,
                "Appointment",
                idempotency_key="booking-42",
            )
            == expected_id
        )

    assert mocked.call_count == 2


def _calendar_conflict(cause):
    try:
        raise CalendarProviderError("Conflict") from cause
    except CalendarProviderError as exc:
        return exc


def test_google_rejects_mismatched_409():
    provider = GoogleCalendarProvider()
    slot = TimeSlot(
        start=datetime(2026, 10, 20, 10, tzinfo=UTC),
        end=datetime(2026, 10, 20, 11, tzinfo=UTC),
    )

    class Connection:
        external_calendar_id = "primary"

    conflict = HTTPError(
        "https://example.com",
        409,
        "Conflict",
        {},
        io.BytesIO(b""),
    )

    with (
        patch.object(provider, "access_token", return_value="token"),
        patch(
            "integrations.calendar.google.request_json",
            side_effect=[
                _calendar_conflict(conflict),
                {
                    "id": "different-event",
                    "summary": "Other appointment",
                },
            ],
        ),
    ):
        with pytest.raises(CalendarProviderError):
            provider.create_event(
                Connection(),
                slot,
                "Appointment",
                idempotency_key="booking-42",
            )
