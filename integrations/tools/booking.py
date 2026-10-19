"""Booking creation tool used by the conversational agent pipeline."""

import logging

from django.db import IntegrityError, OperationalError, transaction

from bookings.models import Booking
from integrations.calendar.base import CalendarProviderError
from integrations.calendar.registry import get_calendar_provider
from integrations.models import CalendarConnection

logger = logging.getLogger(__name__)

SLOT_CONFLICT_CONSTRAINTS = {
    "exclude_overlapping_confirmed_bookings",
    "unique_confirmed_booking_start_per_tenant",
}

DEADLOCK_DETECTED_SQLSTATE = "40P01"


class SlotUnavailableError(Exception):
    """Raised when the requested booking slot is no longer available."""


def _constraint_name(exc: IntegrityError) -> str | None:
    """Return the database constraint responsible for an integrity error."""
    cause = exc.__cause__
    diagnostics = getattr(cause, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def _is_deadlock(exc: OperationalError) -> bool:
    """Return whether PostgreSQL aborted the operation because of a deadlock."""
    cause = exc.__cause__
    return getattr(cause, "sqlstate", None) == DEADLOCK_DETECTED_SQLSTATE


def _sync_external_calendar(booking, tenant, slot, service) -> None:
    """Add the confirmed internal booking to an external calendar when configured."""
    connection = (
        CalendarConnection.objects.filter(tenant=tenant)
        .select_related("tenant")
        .first()
    )

    if connection is None:
        return

    provider = get_calendar_provider(connection)

    if provider is None:
        return

    summary = service.name if service is not None else "Appointment"

    try:
        from integrations.calendar.google import GoogleCalendarProvider
        from integrations.calendar.outlook import OutlookCalendarProvider

        if isinstance(provider, (GoogleCalendarProvider, OutlookCalendarProvider)):
            external_event_id = provider.create_event(
                connection,
                slot,
                summary,
                idempotency_key=f"booking-{booking.pk}",
            )
        else:
            external_event_id = provider.create_event(
                connection,
                slot,
                summary,
            )
    except CalendarProviderError:
        logger.exception(
            "External calendar event creation failed " "booking_id=%s tenant_id=%s",
            booking.pk,
            tenant.pk,
        )
        return

    booking.external_event_id = external_event_id
    booking.save(update_fields=["external_event_id"])


def create_booking(tenant, end_user, slot, service) -> Booking:
    """Create and return a confirmed booking for the requested slot."""
    deadlock_retried = False

    while True:
        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    tenant=tenant,
                    end_user=end_user,
                    service=service,
                    scheduled_start=slot.start,
                    scheduled_end=slot.end,
                    status=Booking.Status.CONFIRMED,
                )

            break

        except IntegrityError as exc:
            if _constraint_name(exc) in SLOT_CONFLICT_CONSTRAINTS:
                raise SlotUnavailableError(
                    "The requested booking slot is no longer available."
                ) from exc

            raise

        except OperationalError as exc:
            if not deadlock_retried and _is_deadlock(exc):
                deadlock_retried = True
                continue

            raise

    _sync_external_calendar(
        booking=booking,
        tenant=tenant,
        slot=slot,
        service=service,
    )

    return booking
