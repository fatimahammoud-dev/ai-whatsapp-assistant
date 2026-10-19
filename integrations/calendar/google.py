"""Google Calendar provider."""

import hashlib
from urllib.error import HTTPError
from urllib.parse import quote

from django.conf import settings

from integrations.calendar.base import (
    CalendarProvider,
    CalendarProviderError,
    TimeSlot,
    parse_datetime,
    token_text,
)
from integrations.calendar.http import request_json

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_FREE_BUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar API v3 implementation."""

    def refresh_access_token(self, connection) -> None:
        if (
            not settings.GOOGLE_CALENDAR_CLIENT_ID
            or not settings.GOOGLE_CALENDAR_CLIENT_SECRET
        ):
            raise CalendarProviderError(
                "Google Calendar OAuth client credentials are not configured."
            )

        payload = request_json(
            GOOGLE_TOKEN_URL,
            method="POST",
            form={
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "refresh_token": token_text(connection.refresh_token),
                "grant_type": "refresh_token",
            },
        )

        self.store_refreshed_tokens(connection, payload)

    def get_busy_intervals(self, connection, date_range) -> list[TimeSlot]:
        token = self.access_token(connection)

        payload = request_json(
            GOOGLE_FREE_BUSY_URL,
            method="POST",
            access_token=token,
            payload={
                "timeMin": date_range.start.isoformat(),
                "timeMax": date_range.end.isoformat(),
                "timeZone": connection.tenant.timezone,
                "items": [{"id": connection.external_calendar_id}],
            },
        )

        calendar_data = payload.get("calendars", {}).get(
            connection.external_calendar_id,
            {},
        )

        return [
            TimeSlot(
                start=parse_datetime(interval["start"]),
                end=parse_datetime(interval["end"]),
            )
            for interval in calendar_data.get("busy", [])
        ]

    def create_event(self, connection, slot, summary, *, idempotency_key=None) -> str:
        token = self.access_token(connection)
        calendar_id = quote(connection.external_calendar_id, safe="")

        event_payload = {
            "summary": summary,
            "start": {"dateTime": slot.start.isoformat()},
            "end": {"dateTime": slot.end.isoformat()},
        }

        if idempotency_key is not None:
            event_payload["id"] = hashlib.sha256(
                str(idempotency_key).encode("utf-8")
            ).hexdigest()[:32]

        events_url = f"{GOOGLE_CALENDAR_BASE_URL}/{calendar_id}/events"

        try:
            if idempotency_key is None:
                payload = request_json(
                    events_url,
                    method="POST",
                    access_token=token,
                    payload=event_payload,
                )
            else:
                payload = request_json(
                    events_url,
                    method="POST",
                    access_token=token,
                    payload=event_payload,
                    retry_safe=True,
                )
        except CalendarProviderError as exc:
            cause = exc.__cause__
            if (
                idempotency_key is None
                or not isinstance(cause, HTTPError)
                or cause.code != 409
            ):
                raise

            expected_id = event_payload["id"]
            existing = request_json(
                f"{events_url}/{quote(expected_id, safe='')}",
                access_token=token,
            )

            if (
                existing.get("id") != expected_id
                or existing.get("summary") != event_payload["summary"]
                or existing.get("start", {}).get("dateTime")
                != event_payload["start"]["dateTime"]
                or existing.get("end", {}).get("dateTime")
                != event_payload["end"]["dateTime"]
            ):
                raise CalendarProviderError(
                    "Conflicting Google event did not match the booking."
                ) from exc

            return expected_id

        event_id = payload.get("id")
        if not event_id:
            raise CalendarProviderError(
                "Google Calendar create-event response did not include an ID."
            )

        return event_id
