"""Availability tools for the conversational booking pipeline."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bookings.models import BlockedDate, Booking


@dataclass(frozen=True)
class TimeSlot:
    """Represent one appointment time window."""

    start: datetime
    end: datetime


def _to_tenant_timezone(value: datetime, tenant_timezone: ZoneInfo) -> datetime:
    """Return a datetime expressed in the tenant's timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=tenant_timezone)

    return value.astimezone(tenant_timezone)


def _parse_working_time(value: str) -> time:
    """Parse a working-hours value such as '09:00'."""
    return datetime.strptime(value, "%H:%M").time()


def _working_hours_for_date(working_hours: dict, day: date):
    """Return the configured opening/closing pair for a local date."""
    normalized = {str(key).lower(): value for key, value in working_hours.items()}

    short_name = day.strftime("%a").lower()
    full_name = day.strftime("%A").lower()

    return normalized.get(short_name) or normalized.get(full_name)


def _merge_intervals(intervals):
    """Merge overlapping busy intervals into non-overlapping ranges."""
    if not intervals:
        return []

    intervals = sorted(intervals, key=lambda interval: interval[0])
    merged = [intervals[0]]

    for start, end in intervals[1:]:
        previous_start, previous_end = merged[-1]

        if start <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))

    return merged


def compute_available_slots(tenant, service, date_range) -> list[TimeSlot]:
    """Compute real appointment availability for a tenant and date range.

    The requested range is treated as half-open: [start, end).
    All calculations are performed in the tenant's configured timezone.
    """
    if date_range is None:
        raise ValueError("date_range is required")

    tenant_timezone = ZoneInfo(tenant.timezone)

    range_start = _to_tenant_timezone(date_range.start, tenant_timezone)
    range_end = _to_tenant_timezone(date_range.end, tenant_timezone)

    if range_end <= range_start:
        return []

    duration_minutes = (
        getattr(service, "duration_minutes", None)
        or tenant.default_slot_duration_minutes
    )
    duration = timedelta(minutes=duration_minutes)
    buffer = timedelta(minutes=tenant.booking_buffer_minutes)

    first_date = range_start.date()
    last_date = (range_end - timedelta(microseconds=1)).date()

    blocked_dates = set(
        BlockedDate.objects.filter(
            tenant=tenant,
            date__range=(first_date, last_date),
        ).values_list("date", flat=True)
    )

    confirmed_bookings = list(
        Booking.objects.filter(
            tenant=tenant,
            status=Booking.Status.CONFIRMED,
            scheduled_start__lt=range_end,
            scheduled_end__gt=range_start,
        ).order_by("scheduled_start")
    )

    available_slots = []
    current_date = first_date

    while current_date <= last_date:
        if current_date in blocked_dates:
            current_date += timedelta(days=1)
            continue

        hours = _working_hours_for_date(tenant.working_hours, current_date)

        if not hours or len(hours) != 2:
            current_date += timedelta(days=1)
            continue

        opening_time = _parse_working_time(hours[0])
        closing_time = _parse_working_time(hours[1])

        window_start = datetime.combine(
            current_date,
            opening_time,
            tzinfo=tenant_timezone,
        )
        window_end = datetime.combine(
            current_date,
            closing_time,
            tzinfo=tenant_timezone,
        )

        if window_end <= window_start:
            current_date += timedelta(days=1)
            continue

        window_start = max(window_start, range_start)
        window_end = min(window_end, range_end)

        if window_start >= window_end:
            current_date += timedelta(days=1)
            continue

        busy_intervals = []

        for booking in confirmed_bookings:
            booking_start = _to_tenant_timezone(
                booking.scheduled_start,
                tenant_timezone,
            )
            booking_end = _to_tenant_timezone(
                booking.scheduled_end,
                tenant_timezone,
            )

            busy_start = booking_start - buffer
            busy_end = booking_end + buffer

            if busy_start < window_end and busy_end > window_start:
                busy_intervals.append(
                    (
                        max(busy_start, window_start),
                        min(busy_end, window_end),
                    )
                )

        busy_intervals = _merge_intervals(busy_intervals)

        free_intervals = []
        free_start = window_start

        for busy_start, busy_end in busy_intervals:
            if free_start < busy_start:
                free_intervals.append((free_start, busy_start))

            free_start = max(free_start, busy_end)

        if free_start < window_end:
            free_intervals.append((free_start, window_end))

        for interval_start, interval_end in free_intervals:
            slot_start = interval_start

            while slot_start + duration <= interval_end:
                slot_end = slot_start + duration

                available_slots.append(
                    TimeSlot(
                        start=slot_start,
                        end=slot_end,
                    )
                )

                slot_start = slot_end + buffer

        current_date += timedelta(days=1)

    return available_slots


def check_availability(tenant, date_range) -> list[TimeSlot]:
    """Return deterministic fake availability until Ticket 2 wires real logic."""
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
