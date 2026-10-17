import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffUser
from integrations.models import CalendarConnection
from tenants.models import Tenant


@pytest.mark.django_db
def test_integrations_requires_login(client):
    response = client.get(reverse("staff-integrations"))

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_integrations_without_connection(client):
    tenant = Tenant.objects.create(
        business_name="Integration Test Business",
        vertical=Tenant.Vertical.DOCTOR,
    )

    user = StaffUser.objects.create_user(
        username="integration-staff",
        password="test-password",
        tenant=tenant,
    )

    client.force_login(user)

    response = client.get(reverse("staff-integrations"))

    assert response.status_code == 200
    assert response.context["connected_provider"] is None
    assert b"Google Calendar" in response.content
    assert b"Microsoft Outlook" in response.content
    assert response.content.count(b"Not connected") == 2


@pytest.mark.django_db
def test_integrations_does_not_show_other_tenant_connection(client):
    own_tenant = Tenant.objects.create(
        business_name="Own Business",
        vertical=Tenant.Vertical.DOCTOR,
    )
    other_tenant = Tenant.objects.create(
        business_name="Other Business",
        vertical=Tenant.Vertical.DOCTOR,
    )

    user = StaffUser.objects.create_user(
        username="own-staff",
        password="test-password",
        tenant=own_tenant,
    )

    CalendarConnection.objects.create(
        tenant=other_tenant,
        provider=Tenant.CalendarProvider.GOOGLE,
        external_calendar_id="other-business-calendar",
        access_token=b"other-access-token",
        refresh_token=b"other-refresh-token",
        token_expires_at=timezone.now(),
    )

    client.force_login(user)

    response = client.get(reverse("staff-integrations"))

    assert response.status_code == 200
    assert response.context["connected_provider"] is None
    assert response.content.count(b"Not connected") == 2
    assert b"other-business-calendar" not in response.content
    assert b"other-access-token" not in response.content
