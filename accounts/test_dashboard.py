from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, Service
from conversations.models import EndUser
from tenants.models import Tenant


def create_booking(
    *,
    tenant,
    end_user,
    service,
    scheduled_start,
    status=Booking.Status.CONFIRMED,
):
    return Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_start + timedelta(minutes=30),
        status=status,
    )


@pytest.mark.django_db
def test_dashboard_shows_only_own_tenant_upcoming_confirmed_bookings(client):
    tenant = Tenant.objects.create(
        business_name="Dashboard Clinic",
        vertical="doctor",
    )
    other_tenant = Tenant.objects.create(
        business_name="Other Clinic",
        vertical="doctor",
    )

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170111111",
        display_name="Future Patient",
    )
    other_end_user = EndUser.objects.create(
        tenant=other_tenant,
        phone_number="+96170222222",
        display_name="Other Patient",
    )

    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )
    other_service = Service.objects.create(
        tenant=other_tenant,
        name="Other Service",
        duration_minutes=30,
    )

    now = timezone.now()

    visible_booking = create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=now + timedelta(hours=2),
    )
    create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=now - timedelta(hours=2),
    )
    create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=now + timedelta(hours=4),
        status=Booking.Status.CANCELLED,
    )
    other_booking = create_booking(
        tenant=other_tenant,
        end_user=other_end_user,
        service=other_service,
        scheduled_start=now + timedelta(hours=3),
    )

    staff = get_user_model().objects.create_user(
        username="dashboard_staff",
        password="test-password-123",
        tenant=tenant,
        role="staff",
    )
    client.force_login(staff)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    assert list(response.context["upcoming_bookings"]) == [visible_booking]
    assert other_booking not in response.context["upcoming_bookings"]


@pytest.mark.django_db
def test_dashboard_orders_upcoming_bookings_by_scheduled_start(client):
    tenant = Tenant.objects.create(
        business_name="Ordering Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170333333",
        display_name="Ordering Patient",
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )

    now = timezone.now()

    later = create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=now + timedelta(hours=4),
    )
    sooner = create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=now + timedelta(hours=2),
    )

    staff = get_user_model().objects.create_user(
        username="ordering_staff",
        password="test-password-123",
        tenant=tenant,
        role="staff",
    )
    client.force_login(staff)

    response = client.get(reverse("dashboard"))

    assert list(response.context["upcoming_bookings"]) == [sooner, later]


@pytest.mark.django_db
def test_dashboard_renders_booking_client_service_and_time(client):
    tenant = Tenant.objects.create(
        business_name="Rendered Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170444444",
        display_name="Rendered Patient",
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Follow-up",
        duration_minutes=30,
    )

    start = timezone.now() + timedelta(days=1)
    create_booking(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=start,
    )

    staff = get_user_model().objects.create_user(
        username="render_staff",
        password="test-password-123",
        tenant=tenant,
        role="staff",
    )
    client.force_login(staff)

    response = client.get(reverse("dashboard"))

    content = response.content.decode()

    assert "Rendered Patient" in content
    assert "Follow-up" in content
    assert timezone.localtime(start).strftime("%Y-%m-%d %H:%M") in content
