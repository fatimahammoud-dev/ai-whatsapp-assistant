"""Availability tools for the conversational booking pipeline."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from bookings.models import BlockedDate, Booking
from integrations.calendar.base import TimeSlot
from integrations.calendar.registry import get_calendar_provider
from integrations.models import CalendarConnection

DEFAULT_WORKING_HOURS = {
    "mon": ["09:00", "17:00"],
    "tue": ["09:00", "17:00"],
    "wed": ["09:00", "17:00"],
    "thu": ["09:00", "17:00"],
    "fri": ["09:00", "17:00"],
}


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

    external_busy_intervals = []

    calendar_connection = (
        CalendarConnection.objects.filter(tenant=tenant)
        .select_related("tenant")
        .first()
    )

    if calendar_connection is not None:
        provider = get_calendar_provider(calendar_connection)

        if provider is not None:
            external_busy_intervals = provider.get_busy_intervals(
                calendar_connection,
                TimeSlot(
                    start=range_start,
                    end=range_end,
                ),
            )

    available_slots = []
    working_hours = tenant.working_hours or DEFAULT_WORKING_HOURS
    current_date = first_date

    while current_date <= last_date:
        if current_date in blocked_dates:
            current_date += timedelta(days=1)
            continue

        hours = _working_hours_for_date(working_hours, current_date)

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

        for external_interval in external_busy_intervals:
            external_start = _to_tenant_timezone(
                external_interval.start,
                tenant_timezone,
            )
            external_end = _to_tenant_timezone(
                external_interval.end,
                tenant_timezone,
            )

            busy_start = external_start - buffer
            busy_end = external_end + buffer

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


def check_availability(tenant, date_range, service=None) -> list[TimeSlot]:
    """Return real computed availability for the tenant.

    When no range is supplied, use the next seven tenant-local calendar days.
    A service is not selected by the mock agent yet, so the tenant's default
    slot duration is used.
    """
    minimum_start = None

    if date_range is None:
        tenant_timezone = ZoneInfo(tenant.timezone)
        minimum_start = timezone.now().astimezone(tenant_timezone)

        range_start = datetime.combine(
            minimum_start.date(),
            time.min,
            tzinfo=tenant_timezone,
        )

        date_range = TimeSlot(
            start=range_start,
            end=range_start + timedelta(days=7),
        )

    slots = compute_available_slots(
        tenant=tenant,
        service=service,
        date_range=date_range,
    )

    if minimum_start is not None:
        slots = [slot for slot in slots if slot.start >= minimum_start]

    return slots
