import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from integrations.models import CalendarConnection
from tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(business_name="Token Clinic", vertical="doctor")


@pytest.fixture
def connection_row(tenant):
    return CalendarConnection.objects.create(
        tenant=tenant,
        provider="google",
        external_calendar_id="cal-1",
        access_token=b"access-token-secret",
        refresh_token=b"refresh-token-secret",
        token_expires_at=timezone.now(),
    )


@pytest.mark.django_db
def test_tokens_round_trip_through_the_database(connection_row):
    stored = CalendarConnection.objects.get(pk=connection_row.pk)

    assert bytes(stored.access_token) == b"access-token-secret"
    assert bytes(stored.refresh_token) == b"refresh-token-secret"


@pytest.mark.django_db
def test_the_raw_column_does_not_contain_the_plaintext(connection_row):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT access_token, refresh_token "
            "FROM integrations_calendarconnection WHERE id = %s",
            [connection_row.pk],
        )
        access_token, refresh_token = cursor.fetchone()

    assert b"access-token-secret" not in bytes(access_token)
    assert b"refresh-token-secret" not in bytes(refresh_token)
    assert bytes(access_token).startswith(b"gAAAAA")


@pytest.mark.django_db
def test_the_whatsapp_token_is_encrypted_too(tenant):
    tenant.whatsapp_access_token = b"whatsapp-secret"
    tenant.save()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT whatsapp_access_token FROM tenants_tenant WHERE id = %s",
            [tenant.pk],
        )
        (stored,) = cursor.fetchone()

    assert b"whatsapp-secret" not in bytes(stored)
    assert bytes(Tenant.objects.get(pk=tenant.pk).whatsapp_access_token) == (
        b"whatsapp-secret"
    )


@pytest.mark.django_db
def test_a_null_token_stays_null(tenant):
    assert tenant.whatsapp_access_token is None
    assert Tenant.objects.get(pk=tenant.pk).whatsapp_access_token is None


@pytest.mark.django_db
def test_two_saves_of_the_same_value_produce_different_ciphertext(tenant):
    """Fernet includes a random IV, so equal tokens must not be linkable."""
    tenant.whatsapp_access_token = b"same-value"
    tenant.save()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT whatsapp_access_token FROM tenants_tenant WHERE id = %s",
            [tenant.pk],
        )
        (first,) = cursor.fetchone()

    tenant.whatsapp_access_token = b"same-value"
    tenant.save()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT whatsapp_access_token FROM tenants_tenant WHERE id = %s",
            [tenant.pk],
        )
        (second,) = cursor.fetchone()

    assert bytes(first) != bytes(second)


@pytest.fixture
def admin_client_(client, db):
    user = get_user_model().objects.create_superuser(
        username="token_admin", password="test-password-123", email="a@b.c"
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_the_admin_cannot_create_a_calendar_connection(admin_client_):
    response = admin_client_.get(reverse("admin:integrations_calendarconnection_add"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_the_admin_shows_a_calendar_connection_read_only(admin_client_, connection_row):
    """View permission still applies, so the page renders without save buttons."""
    response = admin_client_.get(
        reverse(
            "admin:integrations_calendarconnection_change", args=[connection_row.pk]
        )
    )

    assert response.status_code == 200
    assert b'name="_save"' not in response.content
    assert b'name="_continue"' not in response.content


@pytest.mark.django_db
def test_the_admin_rejects_a_posted_change(admin_client_, connection_row):
    response = admin_client_.post(
        reverse(
            "admin:integrations_calendarconnection_change", args=[connection_row.pk]
        ),
        {"external_calendar_id": "changed-by-hand"},
    )

    connection_row.refresh_from_db()

    assert response.status_code in (302, 403)
    assert connection_row.external_calendar_id == "cal-1"
