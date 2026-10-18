from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffUser
from integrations.calendar.base import CalendarProviderError
from integrations.calendar.oauth_views import OAUTH_SESSION_KEY
from integrations.models import CalendarConnection
from tenants.models import Tenant


@pytest.fixture
def owner_client(client, db):
    tenant = Tenant.objects.create(
        business_name="OAuth Test Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    owner = StaffUser.objects.create_user(
        username="oauth-owner",
        password="test-password",
        tenant=tenant,
        role=StaffUser.Role.OWNER,
    )
    client.force_login(owner)
    return client, tenant, owner


def callback_url(provider="google"):
    return reverse("calendar-oauth-callback", kwargs={"provider": provider})


def set_pending(client, tenant, owner, provider="google"):
    session = client.session
    session[OAUTH_SESSION_KEY] = {
        "state": "valid-test-state",
        "code_verifier": "test-verifier",
        "provider": provider,
        "tenant_id": tenant.pk,
        "user_id": owner.pk,
        "redirect_uri": "http://testserver" + callback_url(provider),
    }
    session.save()


@pytest.mark.django_db
def test_callback_requires_login(client):
    response = client.get(callback_url())
    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_callback_rejects_missing_session(owner_client):
    client, tenant, _ = owner_client

    response = client.get(
        callback_url(),
        {"state": "valid-test-state", "code": "code"},
    )

    assert response.status_code == 400
    assert not CalendarConnection.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_callback_rejects_wrong_state(owner_client):
    client, tenant, owner = owner_client
    set_pending(client, tenant, owner)

    with patch("integrations.calendar.oauth.exchange_authorization_code") as exchange:
        response = client.get(
            callback_url(),
            {"state": "wrong-state", "code": "code"},
        )

    assert response.status_code == 400
    exchange.assert_not_called()
    assert not CalendarConnection.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_callback_rejects_other_tenant_session(owner_client):
    client, tenant, owner = owner_client
    other_tenant = Tenant.objects.create(
        business_name="Other Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    set_pending(client, other_tenant, owner)

    response = client.get(
        callback_url(),
        {"state": "valid-test-state", "code": "code"},
    )

    assert response.status_code == 400
    assert not CalendarConnection.objects.filter(tenant=tenant).exists()
    assert not CalendarConnection.objects.filter(tenant=other_tenant).exists()


@pytest.mark.django_db
def test_callback_requires_owner_role(owner_client):
    client, tenant, owner = owner_client
    owner.role = StaffUser.Role.STAFF
    owner.save(update_fields=["role"])
    set_pending(client, tenant, owner)

    response = client.get(
        callback_url(),
        {"state": "valid-test-state", "code": "code"},
    )

    assert response.status_code == 403
    assert not CalendarConnection.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_callback_saves_connection_and_provider(owner_client):
    client, tenant, owner = owner_client
    set_pending(client, tenant, owner)

    tokens = {
        "access_token": "new-access-token",
        "refresh_token": "new-refresh-token",
        "expires_in": 3600,
    }

    with (
        patch(
            "integrations.calendar.oauth.exchange_authorization_code",
            return_value=tokens,
        ),
        patch(
            "integrations.calendar.oauth.discover_calendar_id",
            return_value="calendar-123",
        ),
    ):
        response = client.get(
            callback_url(),
            {"state": "valid-test-state", "code": "code"},
        )

    assert response.status_code == 302

    connection = CalendarConnection.objects.get(tenant=tenant)
    assert connection.provider == Tenant.CalendarProvider.GOOGLE
    assert connection.external_calendar_id == "calendar-123"
    assert bytes(connection.access_token) == b"new-access-token"
    assert bytes(connection.refresh_token) == b"new-refresh-token"
    assert connection.token_expires_at > timezone.now()

    tenant.refresh_from_db()
    assert tenant.calendar_provider == Tenant.CalendarProvider.GOOGLE


@pytest.mark.django_db
def test_failed_discovery_preserves_existing_connection(owner_client):
    client, tenant, owner = owner_client

    original = CalendarConnection.objects.create(
        tenant=tenant,
        provider=Tenant.CalendarProvider.OUTLOOK,
        external_calendar_id="old-calendar",
        access_token=b"old-access",
        refresh_token=b"old-refresh",
        token_expires_at=timezone.now() + timedelta(hours=1),
    )
    tenant.calendar_provider = Tenant.CalendarProvider.OUTLOOK
    tenant.save(update_fields=["calendar_provider"])

    set_pending(client, tenant, owner)

    with (
        patch(
            "integrations.calendar.oauth.exchange_authorization_code",
            return_value={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
        ),
        patch(
            "integrations.calendar.oauth.discover_calendar_id",
            side_effect=CalendarProviderError("Provider unavailable"),
        ),
    ):
        response = client.get(
            callback_url(),
            {"state": "valid-test-state", "code": "code"},
        )

    assert response.status_code == 400

    original.refresh_from_db()
    tenant.refresh_from_db()

    assert original.provider == Tenant.CalendarProvider.OUTLOOK
    assert original.external_calendar_id == "old-calendar"
    assert bytes(original.access_token) == b"old-access"
    assert bytes(original.refresh_token) == b"old-refresh"
    assert tenant.calendar_provider == Tenant.CalendarProvider.OUTLOOK


@pytest.mark.django_db
def test_callback_cannot_reuse_session(owner_client):
    client, tenant, owner = owner_client
    set_pending(client, tenant, owner)

    first = client.get(
        callback_url(),
        {"state": "wrong-state", "code": "code"},
    )
    second = client.get(
        callback_url(),
        {"state": "valid-test-state", "code": "code"},
    )

    assert first.status_code == 400
    assert second.status_code == 400
    assert OAUTH_SESSION_KEY not in client.session
