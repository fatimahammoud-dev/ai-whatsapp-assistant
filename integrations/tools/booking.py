"""Booking creation tool used by the conversational agent pipeline."""

from django.db import IntegrityError, OperationalError, transaction

from bookings.models import Booking

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


def create_booking(tenant, end_user, slot, service) -> Booking:
    """Create and return a confirmed booking for the requested slot."""
    deadlock_retried = False

    while True:
        try:
            with transaction.atomic():
                return Booking.objects.create(
                    tenant=tenant,
                    end_user=end_user,
                    service=service,
                    scheduled_start=slot.start,
                    scheduled_end=slot.end,
                    status=Booking.Status.CONFIRMED,
                )
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
