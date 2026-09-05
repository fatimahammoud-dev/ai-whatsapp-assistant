# Create your tests here.
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from bookings.models import BlockedDate, Booking
from conversations.models import EndUser
from tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(
        business_name="Other Clinic",
        vertical="doctor",
    )


@pytest.fixture
def end_user(tenant):
    return EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170777777",
    )


@pytest.fixture
def start():
    return timezone.now().replace(microsecond=0)


def make_booking(tenant, end_user, start, offset_minutes, duration_minutes, **kwargs):
    return Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start + timedelta(minutes=offset_minutes),
        scheduled_end=start + timedelta(minutes=offset_minutes + duration_minutes),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("offset_minutes", "duration_minutes", "description"),
    [
        (0, 30, "exact duplicate"),
        (1, 30, "starts one minute later"),
        (15, 30, "overlaps the second half"),
        (-10, 20, "overlaps from the left"),
        (5, 15, "fully contained"),
        (-15, 60, "fully contains the existing booking"),
    ],
)
@pytest.mark.django_db
def test_overlapping_confirmed_bookings_are_rejected(
    tenant, end_user, start, offset_minutes, duration_minutes, description
):
    make_booking(tenant, end_user, start, 0, 30)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_booking(tenant, end_user, start, offset_minutes, duration_minutes)


@pytest.mark.django_db
def test_back_to_back_bookings_are_allowed(tenant, end_user, start):
    """The range is half-open, so 10:00-10:30 and 10:30-11:00 do not overlap."""
    make_booking(tenant, end_user, start, 0, 30)

    assert make_booking(tenant, end_user, start, 30, 30).pk is not None


@pytest.mark.django_db
def test_disjoint_bookings_are_allowed(tenant, end_user, start):
    make_booking(tenant, end_user, start, 0, 30)

    assert make_booking(tenant, end_user, start, 90, 30).pk is not None


@pytest.mark.django_db
def test_the_same_slot_is_allowed_for_a_different_tenant(
    tenant, other_tenant, end_user, start
):
    make_booking(tenant, end_user, start, 0, 30)

    other_end_user = EndUser.objects.create(
        tenant=other_tenant,
        phone_number="+96170888888",
    )

    assert make_booking(other_tenant, other_end_user, start, 0, 30).pk is not None


@pytest.mark.django_db
def test_a_cancelled_booking_does_not_block_the_slot(tenant, end_user, start):
    make_booking(tenant, end_user, start, 0, 30, status=Booking.Status.CANCELLED)

    assert make_booking(tenant, end_user, start, 0, 30).pk is not None


@pytest.mark.django_db
def test_cancelling_a_booking_frees_the_slot(tenant, end_user, start):
    booking = make_booking(tenant, end_user, start, 0, 30)

    booking.status = Booking.Status.CANCELLED
    booking.save()

    assert make_booking(tenant, end_user, start, 0, 30).pk is not None


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
