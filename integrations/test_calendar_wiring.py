from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from bookings.models import Booking, Service
from conversations.models import EndUser
from integrations.calendar.base import CalendarProviderError, TimeSlot
from integrations.models import CalendarConnection
from integrations.tools.availability import compute_available_slots
from integrations.tools.booking import create_booking
from tenants.models import Tenant


def _calendar_connection(tenant):
    return CalendarConnection.objects.create(
        tenant=tenant,
        provider=Tenant.CalendarProvider.GOOGLE,
        external_calendar_id="calendar@example.com",
        access_token=b"access-token",
        refresh_token=b"refresh-token",
        token_expires_at=timezone.now() + timedelta(hours=1),
        scopes=["calendar"],
    )


@pytest.mark.django_db
def test_availability_unions_internal_and_external_busy_intervals(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Calendar Clinic",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        working_hours={"thu": ["09:00", "13:00"]},
        default_slot_duration_minutes=60,
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=60,
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170333333",
    )
    connection = _calendar_connection(tenant)

    tenant_timezone = ZoneInfo("Asia/Beirut")

    Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        service=service,
        scheduled_start=datetime(
            2026,
            10,
            1,
            10,
            0,
            tzinfo=tenant_timezone,
        ),
        scheduled_end=datetime(
            2026,
            10,
            1,
            11,
            0,
            tzinfo=tenant_timezone,
        ),
        status=Booking.Status.CONFIRMED,
    )

    class FakeProvider:
        def get_busy_intervals(self, received_connection, date_range):
            assert received_connection.pk == connection.pk
            assert date_range.start.tzinfo is not None
            assert date_range.end.tzinfo is not None

            return [
                TimeSlot(
                    start=datetime(
                        2026,
                        10,
                        1,
                        11,
                        0,
                        tzinfo=tenant_timezone,
                    ),
                    end=datetime(
                        2026,
                        10,
                        1,
                        12,
                        0,
                        tzinfo=tenant_timezone,
                    ),
                )
            ]

    monkeypatch.setattr(
        "integrations.tools.availability.get_calendar_provider",
        lambda received_connection: FakeProvider(),
    )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=TimeSlot(
            start=datetime(
                2026,
                10,
                1,
                0,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                10,
                2,
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
                10,
                1,
                9,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                10,
                1,
                10,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
        TimeSlot(
            start=datetime(
                2026,
                10,
                1,
                12,
                0,
                tzinfo=tenant_timezone,
            ),
            end=datetime(
                2026,
                10,
                1,
                13,
                0,
                tzinfo=tenant_timezone,
            ),
        ),
    ]


@pytest.mark.django_db
def test_create_booking_saves_external_event_id(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Calendar Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170444444",
    )
    _calendar_connection(tenant)

    tenant_timezone = ZoneInfo("Asia/Beirut")
    slot = TimeSlot(
        start=datetime(
            2026,
            10,
            1,
            9,
            0,
            tzinfo=tenant_timezone,
        ),
        end=datetime(
            2026,
            10,
            1,
            9,
            30,
            tzinfo=tenant_timezone,
        ),
    )

    class FakeProvider:
        def create_event(self, connection, received_slot, summary):
            assert connection.tenant_id == tenant.pk
            assert received_slot == slot
            assert summary == "Consultation"
            return "external-event-123"

    monkeypatch.setattr(
        "integrations.tools.booking.get_calendar_provider",
        lambda connection: FakeProvider(),
    )

    booking = create_booking(
        tenant=tenant,
        end_user=end_user,
        slot=slot,
        service=service,
    )

    booking.refresh_from_db()

    assert booking.external_event_id == "external-event-123"


@pytest.mark.django_db
def test_external_calendar_failure_keeps_internal_booking(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Calendar Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170555555",
    )
    _calendar_connection(tenant)

    tenant_timezone = ZoneInfo("Asia/Beirut")
    slot = TimeSlot(
        start=datetime(
            2026,
            10,
            1,
            10,
            0,
            tzinfo=tenant_timezone,
        ),
        end=datetime(
            2026,
            10,
            1,
            10,
            30,
            tzinfo=tenant_timezone,
        ),
    )

    class FailingProvider:
        def create_event(self, connection, received_slot, summary):
            raise CalendarProviderError("provider unavailable")

    monkeypatch.setattr(
        "integrations.tools.booking.get_calendar_provider",
        lambda connection: FailingProvider(),
    )

    booking = create_booking(
        tenant=tenant,
        end_user=end_user,
        slot=slot,
        service=service,
    )

    booking.refresh_from_db()

    assert Booking.objects.filter(pk=booking.pk).exists()
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.external_event_id == ""
