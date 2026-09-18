"""Booking creation tool used by the conversational agent pipeline."""

from django.db import IntegrityError, transaction

from bookings.models import Booking


class BookingSlotUnavailableError(Exception):
    """Raised when a requested booking slot is no longer available."""


def create_booking(tenant, end_user, slot, service) -> Booking:
    """Create and return a confirmed booking for the requested slot."""
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
        raise BookingSlotUnavailableError(
            "The requested booking slot is no longer available."
        ) from exc
