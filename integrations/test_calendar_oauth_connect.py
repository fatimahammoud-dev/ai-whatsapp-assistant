from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import override_settings
from django.urls import reverse

from accounts.models import StaffUser
from integrations.calendar.oauth_views import OAUTH_SESSION_KEY
from integrations.models import CalendarConnection
from tenants.models import Tenant


@pytest.fixture
def owner_client(client, db):
    tenant = Tenant.objects.create(
        business_name="OAuth Connect Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    owner = StaffUser.objects.create_user(
        username="oauth-connect-owner",
        password="test-password",
        tenant=tenant,
        role=StaffUser.Role.OWNER,
    )
    client.force_login(owner)
    return client, tenant, owner


def connect_url(provider):
    return reverse("calendar-oauth-connect", kwargs={"provider": provider})


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("google", "accounts.google.com"),
        ("outlook", "login.microsoftonline.com"),
    ],
)
@override_settings(
    GOOGLE_CALENDAR_CLIENT_ID="google-test-client",
    MICROSOFT_CALENDAR_CLIENT_ID="microsoft-test-client",
    MICROSOFT_CALENDAR_TENANT="common",
)
def test_owner_can_start_oauth_with_pkce(owner_client, provider, expected_host):
    client, tenant, owner = owner_client

    response = client.post(connect_url(provider))

    assert response.status_code == 302

    parsed = urlparse(response.url)
    params = parse_qs(parsed.query)
    pending = client.session[OAUTH_SESSION_KEY]

    assert parsed.hostname == expected_host
    assert params["state"] == [pending["state"]]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0]
    assert pending["provider"] == provider
    assert pending["tenant_id"] == tenant.pk
    assert pending["user_id"] == owner.pk


@pytest.mark.django_db
def test_connect_rejects_get(owner_client):
    client, _, _ = owner_client
    assert client.get(connect_url("google")).status_code == 405


@pytest.mark.django_db
def test_staff_cannot_start_connect(owner_client):
    client, _, owner = owner_client
    owner.role = StaffUser.Role.STAFF
    owner.save(update_fields=["role"])

    assert client.post(connect_url("google")).status_code == 403


@pytest.mark.django_db
def test_unknown_provider_is_rejected(owner_client):
    client, _, _ = owner_client

    assert client.post(connect_url("unknown")).status_code == 400
    assert OAUTH_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_missing_configuration_is_rejected(owner_client):
    client, _, _ = owner_client

    with override_settings(GOOGLE_CALENDAR_CLIENT_ID=""):
        response = client.post(connect_url("google"))

    assert response.status_code == 400
    assert OAUTH_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_callback_persists_granted_scopes(owner_client):
    client, tenant, owner = owner_client

    callback = reverse(
        "calendar-oauth-callback",
        kwargs={"provider": "outlook"},
    )

    session = client.session
    session[OAUTH_SESSION_KEY] = {
        "state": "valid-state",
        "code_verifier": "verifier",
        "provider": "outlook",
        "tenant_id": tenant.pk,
        "user_id": owner.pk,
        "redirect_uri": "http://testserver" + callback,
    }
    session.save()

    with (
        patch(
            "integrations.calendar.oauth.exchange_authorization_code",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "scope": "Calendars.ReadWrite offline_access",
            },
        ),
        patch(
            "integrations.calendar.oauth.discover_calendar_id",
            return_value="calendar-id",
        ),
    ):
        response = client.get(
            callback,
            {"state": "valid-state", "code": "auth-code"},
        )

    assert response.status_code == 302

    connection = CalendarConnection.objects.get(tenant=tenant)
    assert connection.scopes == ["Calendars.ReadWrite", "offline_access"]
