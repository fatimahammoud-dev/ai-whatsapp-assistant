from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from zoneinfo import ZoneInfo

import pytest

import integrations.tools.availability as availability
from bookings.models import Booking
from conversations.models import EndUser
from integrations.tools.availability import TimeSlot, check_availability
from tenants.models import Tenant


@pytest.mark.django_db
def test_check_availability_returns_real_computed_slots():
    tenant = Tenant.objects.create(
        business_name="Real Availability Clinic",
        vertical="doctor",
        timezone="Asia/Beirut",
        working_hours={
            "mon": ["09:00", "12:00"],
        },
        default_slot_duration_minutes=30,
        booking_buffer_minutes=0,
    )

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170111111",
    )

    tenant_timezone = ZoneInfo("Asia/Beirut")

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=datetime(
            2026,
            9,
            28,
            10,
            0,
            tzinfo=tenant_timezone,
        ),
        scheduled_end=datetime(
            2026,
            9,
            28,
            10,
            30,
            tzinfo=tenant_timezone,
        ),
        status=Booking.Status.CONFIRMED,
    )

    slots = check_availability(
        tenant=tenant,
        date_range=TimeSlot(
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
                12,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
    )

    assert slots == [
        TimeSlot(
            start=datetime(2026, 9, 28, 9, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 9, 30, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 9, 30, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 10, 0, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 10, 30, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 11, 0, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 11, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 11, 30, tzinfo=tenant_timezone),
        ),
        TimeSlot(
            start=datetime(2026, 9, 28, 11, 30, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, 12, 0, tzinfo=tenant_timezone),
        ),
    ]


def test_check_availability_uses_default_seven_day_range(monkeypatch):
    fixed_now = datetime(
        2026,
        9,
        28,
        13,
        15,
        tzinfo=datetime_timezone.utc,
    )

    tenant = type(
        "TenantStub",
        (),
        {
            "timezone": "Asia/Beirut",
        },
    )()

    captured = {}

    monkeypatch.setattr(
        availability.timezone,
        "now",
        lambda: fixed_now,
    )

    def fake_compute_available_slots(tenant, service, date_range):
        captured["tenant"] = tenant
        captured["service"] = service
        captured["date_range"] = date_range
        return []

    monkeypatch.setattr(
        availability,
        "compute_available_slots",
        fake_compute_available_slots,
    )

    result = check_availability(
        tenant=tenant,
        date_range=None,
    )

    tenant_timezone = ZoneInfo("Asia/Beirut")
    expected_start = datetime(
        2026,
        9,
        28,
        0,
        0,
        tzinfo=tenant_timezone,
    )

    assert result == []
    assert captured["tenant"] is tenant
    assert captured["service"] is None
    assert captured["date_range"].start == expected_start
    assert captured["date_range"].end == expected_start + timedelta(days=7)


@pytest.mark.django_db
def test_check_availability_uses_default_weekday_working_hours():
    tenant = Tenant.objects.create(
        business_name="Default Hours Clinic",
        vertical="doctor",
        timezone="Asia/Beirut",
        working_hours={},
        default_slot_duration_minutes=60,
        booking_buffer_minutes=0,
    )

    tenant_timezone = ZoneInfo("Asia/Beirut")

    slots = check_availability(
        tenant=tenant,
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
            start=datetime(2026, 9, 28, hour, 0, tzinfo=tenant_timezone),
            end=datetime(2026, 9, 28, hour + 1, 0, tzinfo=tenant_timezone),
        )
        for hour in range(9, 17)
    ]
