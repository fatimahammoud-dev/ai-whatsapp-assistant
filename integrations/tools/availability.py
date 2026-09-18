"""Temporary availability tool used before real calendar integration exists."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeSlot:
    """Represent one available appointment time window."""

    start: datetime
    end: datetime


def check_availability(tenant, date_range) -> list[TimeSlot]:
    """Return deterministic fake availability without accessing a calendar.

    The tenant and requested date range are accepted now so this interface can
    later be backed by the real calendar implementation without changing the
    agent pipeline.
    """
    del tenant, date_range

    return [
        TimeSlot(
            start=datetime(2026, 1, 15, 9, 0),
            end=datetime(2026, 1, 15, 9, 30),
        ),
        TimeSlot(
            start=datetime(2026, 1, 15, 11, 0),
            end=datetime(2026, 1, 15, 11, 30),
        ),
        TimeSlot(
            start=datetime(2026, 1, 15, 14, 0),
            end=datetime(2026, 1, 15, 14, 30),
        ),
    ]
