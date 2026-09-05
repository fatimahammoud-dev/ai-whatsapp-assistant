from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

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
    Booking.objects.create(
        tenant=tenant_b,
        end_user=end_user_b,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    user_model = get_user_model()
    staff_user = user_model.objects.create_user(
        username="staff_a",
        password="test-password-123",
        tenant=tenant_a,
        role="staff",
    )

    client.force_login(staff_user)

    response = client.get(reverse("booking-list"))

    assert response.status_code == 200
    assert list(response.context["bookings"]) == [booking_a]


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
    assert set(response.context["bookings"]) == {
        booking_a,
        booking_b,
    }
