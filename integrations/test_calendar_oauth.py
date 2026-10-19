from urllib.parse import parse_qs, urlparse

import pytest
from django.test import override_settings

from integrations.calendar.oauth import (
    build_authorization_url,
    get_oauth_config,
)
from tenants.models import Tenant


@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        (Tenant.CalendarProvider.GOOGLE, "accounts.google.com"),
        (Tenant.CalendarProvider.OUTLOOK, "login.microsoftonline.com"),
    ],
)
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="google-test-client",
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-test-client",
    MICROSOFT_CALENDAR_TENANT="common",
)
def test_authorization_url_contains_required_parameters(provider, expected_host):
    url = build_authorization_url(
        provider=provider,
        redirect_uri="http://localhost:8000/calendar/callback/",
        state="test-state",
        code_challenge="test-code-challenge",
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.hostname == expected_host
    assert params["response_type"] == ["code"]
    assert params["state"] == ["test-state"]
    assert params["code_challenge"] == ["test-code-challenge"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:8000/calendar/callback/"]


@override_settings(GOOGLE_CALENDAR_CLIENT_ID="google-test-client")
def test_google_requests_offline_access():
    url = build_authorization_url(
        provider=Tenant.CalendarProvider.GOOGLE,
        redirect_uri="http://localhost:8000/callback/",
        state="state",
        code_challenge="challenge",
    )

    params = parse_qs(urlparse(url).query)

    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]

    scopes = params["scope"][0].split()

    assert "https://www.googleapis.com/auth/calendar.events" in scopes
    assert "https://www.googleapis.com/auth/calendar.freebusy" in scopes


@override_settings(
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-test-client",
    MICROSOFT_CALENDAR_TENANT="common",
)
def test_microsoft_requests_calendar_and_refresh_permissions():
    config = get_oauth_config(Tenant.CalendarProvider.OUTLOOK)

    assert "offline_access" in config.scopes
    assert "Calendars.ReadWrite" in config.scopes


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        get_oauth_config("unknown")


@override_settings(GOOGLE_CALENDAR_CLIENT_ID="")
def test_missing_client_id_is_rejected():
    with pytest.raises(ValueError, match="client ID"):
        build_authorization_url(
            provider=Tenant.CalendarProvider.GOOGLE,
            redirect_uri="http://localhost:8000/callback/",
            state="state",
            code_challenge="challenge",
        )
