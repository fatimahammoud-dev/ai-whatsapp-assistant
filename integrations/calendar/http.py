"""Small JSON HTTP helper for calendar providers."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from integrations.calendar.base import CalendarProviderError
from integrations.retry import retry_call


class RetryableCalendarError(CalendarProviderError):
    """Transient calendar HTTP failure."""


def request_json(
    url,
    *,
    method="GET",
    access_token=None,
    payload=None,
    form=None,
    headers=None,
    retry_safe=False,
):
    """Perform one HTTP request and decode its JSON response."""
    request_headers = {
        "Accept": "application/json",
        **(headers or {}),
    }

    if access_token:
        request_headers["Authorization"] = f"Bearer {access_token}"

    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urlencode(form).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )

    def send_request():
        try:
            with urlopen(request, timeout=15) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise RetryableCalendarError(
                    "Temporary calendar HTTP failure."
                ) from exc
            raise CalendarProviderError("Calendar request rejected.") from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise RetryableCalendarError(
                "Temporary calendar connection failure."
            ) from exc

    body = retry_call(
        send_request,
        should_retry=lambda exc: isinstance(exc, RetryableCalendarError),
        attempts=3 if method.upper() == "GET" or retry_safe else 1,
        operation_name="calendar_http",
    )

    if not body:
        return {}

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarProviderError(
            "External calendar returned an invalid JSON response."
        ) from exc
