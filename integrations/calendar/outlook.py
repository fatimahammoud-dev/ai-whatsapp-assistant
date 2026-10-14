"""Microsoft Outlook / Graph calendar provider."""

from datetime import UTC
from urllib.parse import quote, urlencode

from django.conf import settings

from integrations.calendar.base import (
    CalendarProvider,
    CalendarProviderError,
    TimeSlot,
    parse_datetime,
    token_text,
)
from integrations.calendar.http import request_json

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class OutlookCalendarProvider(CalendarProvider):
    """Microsoft Graph implementation for Outlook calendars."""

    def refresh_access_token(self, connection) -> None:
        if (
            not settings.MICROSOFT_CALENDAR_CLIENT_ID
            or not settings.MICROSOFT_CALENDAR_CLIENT_SECRET
        ):
            raise CalendarProviderError(
                "Microsoft Calendar OAuth client credentials are not configured."
            )

        tenant = quote(settings.MICROSOFT_CALENDAR_TENANT, safe="")
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

        form = {
            "client_id": settings.MICROSOFT_CALENDAR_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CALENDAR_CLIENT_SECRET,
            "refresh_token": token_text(connection.refresh_token),
            "grant_type": "refresh_token",
        }

        if connection.scopes:
            form["scope"] = " ".join(connection.scopes)

        payload = request_json(
            token_url,
            method="POST",
            form=form,
        )

        self.store_refreshed_tokens(connection, payload)

    def get_busy_intervals(self, connection, date_range) -> list[TimeSlot]:
        token = self.access_token(connection)
        calendar_id = quote(connection.external_calendar_id, safe="")

        query = urlencode(
            {
                "startDateTime": date_range.start.isoformat(),
                "endDateTime": date_range.end.isoformat(),
                "$select": "start,end,showAs,isCancelled",
            }
        )

        next_url = f"{GRAPH_BASE_URL}/me/calendars/{calendar_id}/calendarView?{query}"
        intervals = []

        while next_url:
            payload = request_json(
                next_url,
                access_token=token,
                headers={"Prefer": 'outlook.timezone="UTC"'},
            )

            for event in payload.get("value", []):
                if event.get("isCancelled"):
                    continue

                if event.get("showAs") == "free":
                    continue

                intervals.append(
                    TimeSlot(
                        start=parse_datetime(event["start"]["dateTime"]),
                        end=parse_datetime(event["end"]["dateTime"]),
                    )
                )

            next_url = payload.get("@odata.nextLink")

        return intervals

    def create_event(self, connection, slot, summary) -> str:
        token = self.access_token(connection)
        calendar_id = quote(connection.external_calendar_id, safe="")

        start = slot.start.astimezone(UTC)
        end = slot.end.astimezone(UTC)

        payload = request_json(
            f"{GRAPH_BASE_URL}/me/calendars/{calendar_id}/events",
            method="POST",
            access_token=token,
            payload={
                "subject": summary,
                "start": {
                    "dateTime": start.replace(tzinfo=None).isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": end.replace(tzinfo=None).isoformat(),
                    "timeZone": "UTC",
                },
            },
        )

        event_id = payload.get("id")
        if not event_id:
            raise CalendarProviderError(
                "Microsoft Graph create-event response did not include an ID."
            )

        return event_id
