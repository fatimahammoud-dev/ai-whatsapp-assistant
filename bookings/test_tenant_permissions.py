from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView

from accounts.mixins import TenantScopedMixin
from accounts.models import StaffUser
from bookings.models import Booking
from conversations.models import EndUser
from tenants.models import Tenant


@pytest.mark.django_db
def test_staff_user_only_sees_own_tenant_bookings(client):
    tenant_a = Tenant.objects.create(
        business_name="Clinic A",
        vertical="doctor",
    )
    tenant_b = Tenant.objects.create(
        business_name="Clinic B",
        vertical="doctor",
    )

    end_user_a = EndUser.objects.create(
        tenant=tenant_a,
        phone_number="+96170111111",
    )
    end_user_b = EndUser.objects.create(
        tenant=tenant_b,
        phone_number="+96170222222",
    )

    start = timezone.now()

    booking_a = Booking.objects.create(
        tenant=tenant_a,
        end_user=end_user_a,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )
    booking_b = Booking.objects.create(
        tenant=tenant_b,
        end_user=end_user_b,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    user_model = get_user_model()

    staff_a = user_model.objects.create_user(
        username="staff_a",
        password="test-password-123",
        tenant=tenant_a,
        role="staff",
    )

    user_model.objects.create_user(
        username="staff_b",
        password="test-password-123",
        tenant=tenant_b,
        role="staff",
    )

    client.force_login(staff_a)

    response = client.get(reverse("booking-list"))

    assert response.status_code == 200

    bookings = list(response.context["bookings"])

    assert booking_a in bookings
    assert booking_b not in bookings

    assert b"Clinic A" in response.content
    assert b"Clinic B" not in response.content


@pytest.mark.django_db
def test_platform_admin_can_see_all_tenant_bookings(client):
    tenant_a = Tenant.objects.create(
        business_name="Clinic A",
        vertical="doctor",
    )
    tenant_b = Tenant.objects.create(
        business_name="Clinic B",
        vertical="doctor",
    )

    end_user_a = EndUser.objects.create(
        tenant=tenant_a,
        phone_number="+96170333333",
    )
    end_user_b = EndUser.objects.create(
        tenant=tenant_b,
        phone_number="+96170444444",
    )

    start = timezone.now()

    booking_a = Booking.objects.create(
        tenant=tenant_a,
        end_user=end_user_a,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )
    booking_b = Booking.objects.create(
        tenant=tenant_b,
        end_user=end_user_b,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    user_model = get_user_model()

    platform_admin = user_model.objects.create_user(
        username="platform_admin",
        password="test-password-123",
        role="platform_admin",
    )

    client.force_login(platform_admin)

    response = client.get(reverse("booking-list"))

    assert response.status_code == 200

    bookings = list(response.context["bookings"])

    assert booking_a in bookings
    assert booking_b in bookings

    assert b"Clinic A" in response.content
    assert b"Clinic B" in response.content


@pytest.mark.django_db
def test_a_django_superuser_sees_every_tenants_bookings(client):
    """createsuperuser never sets `role`, so a superuser is role="staff" with
    no tenant. Without the is_superuser check it saw nothing at all."""
    tenant_a = Tenant.objects.create(business_name="Clinic A", vertical="doctor")
    tenant_b = Tenant.objects.create(business_name="Clinic B", vertical="doctor")

    end_user_a = EndUser.objects.create(tenant=tenant_a, phone_number="+96170555001")
    end_user_b = EndUser.objects.create(tenant=tenant_b, phone_number="+96170555002")

    start = timezone.now()

    booking_a = Booking.objects.create(
        tenant=tenant_a,
        end_user=end_user_a,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )
    booking_b = Booking.objects.create(
        tenant=tenant_b,
        end_user=end_user_b,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    superuser = get_user_model().objects.create_superuser(
        username="scoping_superuser",
        password="test-password-123",
        email="superuser@example.com",
    )

    assert superuser.role == StaffUser.Role.STAFF
    assert superuser.tenant_id is None

    client.force_login(superuser)

    response = client.get(reverse("booking-list"))

    assert response.status_code == 200
    assert set(response.context["bookings"]) == {booking_a, booking_b}


@pytest.mark.django_db
def test_a_staff_user_without_a_tenant_sees_nothing(client):
    tenant = Tenant.objects.create(business_name="Clinic A", vertical="doctor")
    end_user = EndUser.objects.create(tenant=tenant, phone_number="+96170555003")

    start = timezone.now()

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    orphan = get_user_model().objects.create_user(
        username="scoping_orphan",
        password="test-password-123",
        role="staff",
    )

    client.force_login(orphan)

    response = client.get(reverse("booking-list"))

    assert response.status_code == 200
    assert list(response.context["bookings"]) == []


@pytest.mark.django_db
def test_an_anonymous_visitor_is_redirected_to_login(client):
    response = client.get(reverse("booking-list"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_the_mixin_returns_nothing_for_an_anonymous_user():
    """AnonymousUser has no `.role`. Reading it used to raise AttributeError,
    which only stayed hidden because BookingListView lists LoginRequiredMixin
    first. The mixin must fail closed on its own."""

    class BareView(TenantScopedMixin, ListView):
        model = Booking

    request = RequestFactory().get("/bookings/")
    request.user = AnonymousUser()

    view = BareView()
    view.request = request

    assert list(view.get_queryset()) == []
