from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bookings.models import BlockedDate, Booking, Service
from conversations.models import EndUser
from integrations.tools.availability import TimeSlot, compute_available_slots
from tenants.models import Tenant


@pytest.mark.django_db
def test_compute_available_slots_returns_exact_remaining_open_slots():
    tenant = Tenant.objects.create(
        business_name="Availability Clinic",
        vertical="doctor",
        timezone="Asia/Beirut",
        working_hours={
            "mon": ["09:00", "13:00"],
            "tue": ["09:00", "13:00"],
        },
        default_slot_duration_minutes=30,
        booking_buffer_minutes=15,
    )

    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=60,
    )

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170123456",
    )

    tenant_timezone = ZoneInfo("Asia/Beirut")

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(
            2026,
            9,
            28,
            10,
            15,
            tzinfo=tenant_timezone,
        ),
        scheduled_end=datetime(
            2026,
            9,
            28,
            11,
            15,
            tzinfo=tenant_timezone,
        ),
        status=Booking.Status.CONFIRMED,
    )

    BlockedDate.objects.create(
        tenant=tenant,
        date=datetime(2026, 9, 29).date(),
        reason="Clinic closed",
    )

    date_range = TimeSlot(
        start=datetime(
            2026,
            9,
            28,
            0,
            0,
            tzinfo=tenant_timezone,
        ),
        end=datetime(
            2026,
            9,
            30,
            0,
            0,
            tzinfo=tenant_timezone,
        ),
    )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=date_range,
    )

    assert slots == [
        TimeSlot(
            start=datetime(
                2026,
                9,
                28,
                9,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                9,
                28,
                10,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
        TimeSlot(
            start=datetime(
                2026,
                9,
                28,
                11,
                30,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                9,
                28,
                12,
                30,
                tzinfo=tenant_timezone,
            ),
        ),
    ]


@pytest.mark.django_db
def test_compute_available_slots_uses_tenant_default_duration_when_missing():
    tenant = Tenant.objects.create(
        business_name="Default Duration Clinic",
        vertical="doctor",
        timezone="Asia/Beirut",
        working_hours={
            "mon": ["09:00", "10:00"],
        },
        default_slot_duration_minutes=30,
        booking_buffer_minutes=0,
    )

    service_without_duration = SimpleNamespace(duration_minutes=None)
    tenant_timezone = ZoneInfo("Asia/Beirut")

    slots = compute_available_slots(
        tenant=tenant,
        service=service_without_duration,
        date_range=TimeSlot(
            start=datetime(
                2026,
                9,
                28,
                0,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                9,
                29,
                0,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
    )

    assert slots == [
        TimeSlot(
            start=datetime(
                2026,
                9,
                28,
                9,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                9,
                28,
                9,
                30,
                tzinfo=tenant_timezone,
            ),
        ),
        TimeSlot(
            start=datetime(
                2026,
                9,
                28,
                9,
                30,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                9,
                28,
                10,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
    ]
