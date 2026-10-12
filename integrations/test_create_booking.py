from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking, Service
from conversations.models import EndUser
from integrations.tools.availability import TimeSlot
from integrations.tools.booking import (
    BookingSlotUnavailableError,
    create_booking,
)
from tenants.models import Tenant


@pytest.fixture
def booking_data(db):
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170123456",
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )

    start = timezone.now().replace(microsecond=0)
    slot = TimeSlot(
        start=start,
        end=start + timedelta(minutes=30),
    )

    return tenant, end_user, service, slot


def test_create_booking_creates_confirmed_booking(booking_data):
    tenant, end_user, service, slot = booking_data

    booking = create_booking(
        tenant=tenant,
        end_user=end_user,
        slot=slot,
        service=service,
    )

    booking.refresh_from_db()

    assert booking.tenant == tenant
    assert booking.end_user == end_user
    assert booking.service == service
    assert booking.scheduled_start == slot.start
    assert booking.scheduled_end == slot.end
    assert booking.status == Booking.Status.CONFIRMED


def test_create_booking_raises_clear_error_when_slot_is_taken(booking_data):
    tenant, end_user, service, slot = booking_data

    create_booking(
        tenant=tenant,
        end_user=end_user,
        slot=slot,
        service=service,
    )

    with pytest.raises(
        BookingSlotUnavailableError,
        match="no longer available",
    ):
        create_booking(
            tenant=tenant,
            end_user=end_user,
            slot=slot,
            service=service,
        )

    assert Booking.objects.count() == 1
