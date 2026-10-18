from unittest.mock import patch

import pytest
from django.test import override_settings

from integrations.calendar.base import CalendarProviderError
from integrations.calendar.oauth import (
    discover_calendar_id,
    exchange_authorization_code,
)
from tenants.models import Tenant


@pytest.mark.parametrize(
    ("provider", "expected_url"),
    [
        (
            Tenant.CalendarProvider.GOOGLE,
            "https://oauth2.googleapis.com/token",
        ),
        (
            Tenant.CalendarProvider.OUTLOOK,
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        ),
    ],
)
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="google-test-id",
    GOOGLE_CALENDAR_CLIENT_SECRET="google-test-secret",
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-test-id",
    MICROSOFT_CALENDAR_CLIENT_SECRET="microsoft-test-secret",
    MICROSOFT_CALENDAR_TENANT="common",
)
def test_exchange_sends_code_and_pkce_verifier(provider, expected_url):
    with patch(
        "integrations.calendar.http.request_json",
        return_value={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600,
        },
    ) as request_mock:
        result = exchange_authorization_code(
            provider=provider,
            code="test-auth-code",
            redirect_uri="http://localhost:8000/callback/",
            code_verifier="test-pkce-verifier",
        )

    assert result["access_token"] == "test-access-token"

    request_mock.assert_called_once()
    args, kwargs = request_mock.call_args

    assert args[0] == expected_url
    assert kwargs["method"] == "POST"
    assert kwargs["form"]["code"] == "test-auth-code"
    assert kwargs["form"]["code_verifier"] == "test-pkce-verifier"
    assert kwargs["form"]["grant_type"] == "authorization_code"


@pytest.mark.parametrize(
    ("provider", "expected_url"),
    [
        (
            Tenant.CalendarProvider.GOOGLE,
            "https://www.googleapis.com/calendar/v3/users/me/calendarList/primary",
        ),
        (
            Tenant.CalendarProvider.OUTLOOK,
            "https://graph.microsoft.com/v1.0/me/calendar",
        ),
    ],
)
def test_discover_calendar_id(provider, expected_url):
    with patch(
        "integrations.calendar.http.request_json",
        return_value={"id": "calendar-123"},
    ) as request_mock:
        result = discover_calendar_id(
            provider=provider,
            access_token="test-access-token",
        )

    assert result == "calendar-123"
    request_mock.assert_called_once_with(
        expected_url,
        access_token="test-access-token",
    )


@pytest.mark.parametrize(
    "payload",
    [{}, {"id": ""}, {"id": None}, {"id": 123}],
)
def test_discover_rejects_missing_or_invalid_calendar_id(payload):
    with patch(
        "integrations.calendar.http.request_json",
        return_value=payload,
    ):
        with pytest.raises(CalendarProviderError, match="usable calendar ID"):
            discover_calendar_id(
                provider=Tenant.CalendarProvider.GOOGLE,
                access_token="test-access-token",
            )


@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="",
    GOOGLE_CALENDAR_CLIENT_SECRET="",
)
def test_exchange_rejects_missing_credentials():
    with pytest.raises(ValueError, match="credentials"):
        exchange_authorization_code(
            provider=Tenant.CalendarProvider.GOOGLE,
            code="test-code",
            redirect_uri="http://localhost:8000/callback/",
            code_verifier="test-verifier",
        )


def test_exchange_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported"):
        exchange_authorization_code(
            provider="unknown",
            code="test-code",
            redirect_uri="http://localhost:8000/callback/",
            code_verifier="test-verifier",
        )
