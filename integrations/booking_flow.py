"""Helpers for multi-turn booking state and tool argument adaptation."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bookings.models import Service
from conversations.models import Conversation
from integrations.calendar.base import TimeSlot

TOOL_STATE_FIELDS = {
    "ask_clarification": (
        "service_name",
        "date",
        "time_preference",
    ),
    "check_availability": (
        "service_name",
        "date",
        "time_preference",
    ),
    "create_booking": (
        "service_name",
        "slot_start",
        "slot_end",
    ),
}


def pending_updates_from_tool(tool_name, tool_args):
    """Extract booking details that should survive into the next turn."""
    fields = TOOL_STATE_FIELDS.get(tool_name, ())

    if not fields:
        return {}

    updates = {"intent": "booking"}

    for field in fields:
        value = tool_args.get(field)

        if value not in (None, ""):
            updates[field] = value

    return updates


def merge_pending_state(conversation, updates, awaiting=True):
    """Merge booking details into Conversation.pending_intent_state."""
    state = dict(conversation.pending_intent_state or {})

    for key, value in updates.items():
        if value not in (None, ""):
            state[key] = value

    conversation.pending_intent_state = state

    update_fields = ["pending_intent_state"]

    if awaiting:
        conversation.status = Conversation.Status.AWAITING_USER
        update_fields.append("status")

    conversation.save(update_fields=update_fields)

    return state


def clear_pending_state(conversation):
    """Clear completed booking state and return the conversation to active."""
    conversation.pending_intent_state = {}
    conversation.status = Conversation.Status.ACTIVE
    conversation.save(
        update_fields=[
            "pending_intent_state",
            "status",
        ]
    )


def date_range_for_date(tenant, date_text):
    """Convert YYYY-MM-DD into one tenant-local calendar-day range."""
    requested_date = date.fromisoformat(date_text)
    tenant_timezone = ZoneInfo(tenant.timezone)

    start = datetime.combine(
        requested_date,
        time.min,
        tzinfo=tenant_timezone,
    )

    return TimeSlot(
        start=start,
        end=start + timedelta(days=1),
    )


def resolve_service(tenant, service_name):
    """Resolve an active tenant service by its user-facing name."""
    if not service_name:
        return None

    return (
        Service.objects.filter(
            tenant=tenant,
            is_active=True,
            name__iexact=service_name,
        )
        .order_by("pk")
        .first()
    )


def filter_slots_by_time_preference(slots, tenant, preference):
    """Apply the LLM's broad time-of-day preference to real slots."""
    if not preference or preference == "any":
        return list(slots)

    tenant_timezone = ZoneInfo(tenant.timezone)
    filtered = []

    for slot in slots:
        local_hour = slot.start.astimezone(tenant_timezone).hour

        if preference == "morning" and local_hour < 12:
            filtered.append(slot)
        elif preference == "afternoon" and 12 <= local_hour < 17:
            filtered.append(slot)
        elif preference == "evening" and local_hour >= 17:
            filtered.append(slot)

    return filtered


def serialize_slots(slots):
    """Store backend-offered slots safely inside JSON conversation state."""
    return [
        {
            "start": slot.start.isoformat(),
            "end": slot.end.isoformat(),
        }
        for slot in slots
    ]


def parse_slot(tenant, start_text, end_text):
    """Convert LLM ISO datetime strings into a TimeSlot."""
    tenant_timezone = ZoneInfo(tenant.timezone)

    start = datetime.fromisoformat(start_text)
    end = datetime.fromisoformat(end_text)

    if start.tzinfo is None:
        start = start.replace(tzinfo=tenant_timezone)

    if end.tzinfo is None:
        end = end.replace(tzinfo=tenant_timezone)

    return TimeSlot(
        start=start,
        end=end,
    )


def slot_was_offered(slot, offered_slots):
    """Return whether the selected slot came from real availability results."""
    for offered in offered_slots or []:
        offered_start = datetime.fromisoformat(offered["start"])
        offered_end = datetime.fromisoformat(offered["end"])

        if offered_start == slot.start and offered_end == slot.end:
            return True

    return False


MAX_OFFERED_SLOTS = 3


def select_offered_slots(slots, tenant):
    """Select up to three earliest slots and track the last offered day."""
    ordered_slots = sorted(slots, key=lambda slot: slot.start)
    offered = ordered_slots[:MAX_OFFERED_SLOTS]

    if not offered:
        return [], None

    tenant_timezone = ZoneInfo(tenant.timezone)
    last_offered_date = offered[-1].start.astimezone(tenant_timezone).date().isoformat()

    return offered, last_offered_date


def next_availability_range(tenant, last_offered_date, days=7):
    """Search a bounded block of days after the last offered day."""
    start_date = date.fromisoformat(last_offered_date) + timedelta(days=1)
    tenant_timezone = ZoneInfo(tenant.timezone)

    start = datetime.combine(
        start_date,
        time.min,
        tzinfo=tenant_timezone,
    )

    return TimeSlot(
        start=start,
        end=start + timedelta(days=days),
    )
