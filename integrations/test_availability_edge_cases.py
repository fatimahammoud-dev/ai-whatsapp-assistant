from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from bookings.models import BlockedDate, Booking, Service
from conversations.models import EndUser
from integrations.tools.availability import TimeSlot, compute_available_slots
from tenants.models import Tenant


def _create_tenant(**overrides):
    defaults = {
        "business_name": "Edge Case Clinic",
        "vertical": "doctor",
        "timezone": "Asia/Beirut",
        "working_hours": {"mon": ["09:00", "13:00"]},
        "default_slot_duration_minutes": 30,
        "booking_buffer_minutes": 0,
    }
    defaults.update(overrides)
    return Tenant.objects.create(**defaults)


def _create_service(tenant, duration_minutes=60):
    return Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=duration_minutes,
    )


def _create_end_user(tenant, phone_number="+96170999999"):
    return EndUser.objects.create(
        tenant=tenant,
        phone_number=phone_number,
    )


@pytest.mark.django_db
def test_fully_booked_day_returns_no_available_slots():
    tenant = _create_tenant(
        working_hours={"mon": ["09:00", "11:00"]},
    )
    service = _create_service(tenant, duration_minutes=60)
    end_user = _create_end_user(tenant)

    tenant_timezone = ZoneInfo("Asia/Beirut")

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(2026, 9, 28, 9, 0, tzinfo=tenant_timezone),
        scheduled_end=datetime(2026, 9, 28, 10, 0, tzinfo=tenant_timezone),
        status=Booking.Status.CONFIRMED,
    )

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(2026, 9, 28, 10, 0, tzinfo=tenant_timezone),
        scheduled_end=datetime(2026, 9, 28, 11, 0, tzinfo=tenant_timezone),
        status=Booking.Status.CONFIRMED,
    )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=TimeSlot(
            start=datetime(2026, 9, 28, 0, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 29, 0, 0, tzinfo=tenant_timezone),
        ),
    )

    assert slots == []


@pytest.mark.django_db
def test_blocked_date_excludes_otherwise_open_day():
    tenant = _create_tenant(
        working_hours={"mon": ["09:00", "12:00"]},
    )
    service = _create_service(tenant, duration_minutes=60)

    tenant_timezone = ZoneInfo("Asia/Beirut")

    BlockedDate.objects.create(
        tenant=tenant,
        date=datetime(2026, 9, 28).date(),
        reason="Closed for the day",
    )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=TimeSlot(
            start=datetime(2026, 9, 28, 0, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 29, 0, 0, tzinfo=tenant_timezone),
        ),
    )

    assert slots == []


@pytest.mark.django_db
def test_back_to_back_bookings_with_buffer_do_not_create_false_gap():
    tenant = _create_tenant(
        working_hours={"mon": ["09:00", "13:00"]},
        booking_buffer_minutes=15,
    )
    service = _create_service(tenant, duration_minutes=30)
    end_user = _create_end_user(tenant)

    tenant_timezone = ZoneInfo("Asia/Beirut")

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(2026, 9, 28, 10, 0, tzinfo=tenant_timezone),
        scheduled_end=datetime(2026, 9, 28, 10, 30, tzinfo=tenant_timezone),
        status=Booking.Status.CONFIRMED,
    )

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(2026, 9, 28, 10, 30, tzinfo=tenant_timezone),
        scheduled_end=datetime(2026, 9, 28, 11, 0, tzinfo=tenant_timezone),
        status=Booking.Status.CONFIRMED,
    )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=TimeSlot(
            start=datetime(2026, 9, 28, 9, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 13, 0, tzinfo=tenant_timezone),
        ),
    )

    assert slots == [
        TimeSlot(
            start=datetime(2026, 9, 28, 9, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 9, 30, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 11, 15, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 11, 45, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 12, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 12, 30, tzinfo=tenant_timezone),
        ),
    ]


@pytest.mark.django_db
def test_date_range_boundary_is_interpreted_in_tenant_timezone():
    tenant = _create_tenant(
        working_hours={"mon": ["09:00", "10:00"]},
    )
    service = _create_service(tenant, duration_minutes=60)

    tenant_timezone = ZoneInfo("Asia/Beirut")

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=TimeSlot(
            start=datetime(2026, 9, 27, 21, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 28, 21, 0, tzinfo=timezone.utc),
        ),
    )

    assert slots == [
        TimeSlot(
            start=datetime(2026, 9, 28, 9, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 10, 0, tzinfo=tenant_timezone),
        )
    ]
