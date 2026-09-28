"""Small JSON HTTP helper for calendar providers."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from integrations.calendar.base import CalendarProviderError


def request_json(
    url,
    *,
    method="GET",
    access_token=None,
    payload=None,
    form=None,
    headers=None,
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

    try:
        with urlopen(request, timeout=15) as response:
            body = response.read()
    except OSError as exc:
        raise CalendarProviderError("External calendar request failed.") from exc

    if not body:
        return {}

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarProviderError(
            "External calendar returned an invalid JSON response."
        ) from exc
