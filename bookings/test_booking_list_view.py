from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from bookings.views import BookingListView
from conversations.models import EndUser
from tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(business_name="List Clinic", vertical="doctor")


@pytest.fixture
def end_user(tenant):
    return EndUser.objects.create(tenant=tenant, phone_number="+96170666666")


@pytest.fixture
def staff_client(client, tenant):
    user = get_user_model().objects.create_user(
        username="list_staff",
        password="test-password-123",
        tenant=tenant,
        role="staff",
    )
    client.force_login(user)
    return client


def make_bookings(tenant, end_user, count, spacing_minutes=60):
    start = timezone.now().replace(microsecond=0)
    return [
        Booking.objects.create(
            tenant=tenant,
            end_user=end_user,
            scheduled_start=start + timedelta(minutes=i * spacing_minutes),
            scheduled_end=start + timedelta(minutes=i * spacing_minutes + 30),
        )
        for i in range(count)
    ]


@pytest.mark.django_db
def test_bookings_are_ordered_by_scheduled_start(tenant, end_user, staff_client):
    created = make_bookings(tenant, end_user, 3)
    shuffled = [created[2], created[0], created[1]]
    assert {b.pk for b in shuffled} == {b.pk for b in created}

    response = staff_client.get(reverse("booking-list"))

    assert list(response.context["bookings"]) == created


@pytest.mark.django_db
def test_the_booking_list_is_paginated(tenant, end_user, staff_client):
    make_bookings(tenant, end_user, BookingListView.paginate_by + 5)

    response = staff_client.get(reverse("booking-list"))

    assert response.status_code == 200
    assert response.context["is_paginated"] is True
    assert len(response.context["bookings"]) == BookingListView.paginate_by


@pytest.mark.django_db
def test_the_second_page_holds_the_remainder(tenant, end_user, staff_client):
    total = BookingListView.paginate_by + 5
    make_bookings(tenant, end_user, total)

    response = staff_client.get(reverse("booking-list"), {"page": 2})

    assert response.status_code == 200
    assert len(response.context["bookings"]) == total - BookingListView.paginate_by
