from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections, transaction

from bookings.models import Booking, Service
from conversations.models import EndUser
from integrations.tools.availability import TimeSlot
from integrations.tools.booking import SlotUnavailableError, create_booking
from tenants.models import Tenant


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_booking_attempts_create_exactly_one_booking():
    tenant = Tenant.objects.create(
        business_name="Concurrency Clinic",
        vertical=Tenant.Vertical.DOCTOR,
    )
    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
    )
    first_end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170111111",
    )
    second_end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170222222",
    )

    slot_start = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    slot = TimeSlot(
        start=slot_start,
        end=slot_start + timedelta(minutes=30),
    )

    barrier = Barrier(2, timeout=5)

    def attempt_booking(end_user_id):
        close_old_connections()

        try:
            with transaction.atomic():
                thread_tenant = Tenant.objects.get(pk=tenant.pk)
                thread_service = Service.objects.get(pk=service.pk)
                thread_end_user = EndUser.objects.get(pk=end_user_id)

                # Both database transactions must reach this point before
                # either thread is allowed to attempt the booking.
                barrier.wait()

                try:
                    booking = create_booking(
                        tenant=thread_tenant,
                        end_user=thread_end_user,
                        slot=slot,
                        service=thread_service,
                    )
                except SlotUnavailableError:
                    return "unavailable"

                return f"created:{booking.pk}"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt_booking, first_end_user.pk),
            executor.submit(attempt_booking, second_end_user.pk),
        ]
        results = [future.result(timeout=15) for future in futures]

    created_results = [result for result in results if result.startswith("created:")]

    assert len(created_results) == 1
    assert results.count("unavailable") == 1

    assert (
        Booking.objects.filter(
            tenant=tenant,
            scheduled_start=slot.start,
            scheduled_end=slot.end,
            status=Booking.Status.CONFIRMED,
        ).count()
        == 1
    )
