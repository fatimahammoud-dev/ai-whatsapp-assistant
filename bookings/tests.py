# Create your tests here.
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from bookings.models import BlockedDate, Booking
from conversations.models import EndUser
from tenants.models import Tenant


@pytest.mark.django_db
def test_confirmed_booking_start_is_unique_per_tenant():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170111111",
    )

    start = timezone.now()
    end = start + timedelta(minutes=30)

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=end,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Booking.objects.create(
                tenant=tenant,
                end_user=end_user,
                scheduled_start=start,
                scheduled_end=end,
            )


@pytest.mark.django_db
def test_bookings_can_be_queried_by_tenant_and_date_range():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170222222",
    )

    start = timezone.now()

    booking = Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    bookings = Booking.objects.filter(
        tenant=tenant,
        scheduled_start__range=(
            start - timedelta(hours=1),
            start + timedelta(hours=1),
        ),
    )

    assert list(bookings) == [booking]


@pytest.mark.django_db
def test_booking_end_must_be_after_start():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170333333",
    )

    start = timezone.now()

    booking = Booking(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=start,
    )

    with pytest.raises(ValidationError):
        booking.clean()


@pytest.mark.django_db
def test_blocked_date_is_unique_per_tenant():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )

    blocked_date = timezone.now().date()

    BlockedDate.objects.create(
        tenant=tenant,
        date=blocked_date,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BlockedDate.objects.create(
                tenant=tenant,
                date=blocked_date,
            )


@pytest.mark.django_db
def test_booking_end_before_start_is_rejected_by_the_database():
    """clean() only runs through forms; direct saves must still be rejected."""
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170444444",
    )

    start = timezone.now()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Booking.objects.create(
                tenant=tenant,
                end_user=end_user,
                scheduled_start=start,
                scheduled_end=start - timedelta(minutes=30),
            )


@pytest.mark.django_db
def test_booking_with_equal_start_and_end_is_rejected_by_the_database():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170555555",
    )

    start = timezone.now()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Booking.objects.create(
                tenant=tenant,
                end_user=end_user,
                scheduled_start=start,
                scheduled_end=start,
            )
