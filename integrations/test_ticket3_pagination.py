from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from integrations.booking_flow import (
    next_availability_range,
    select_offered_slots,
)


def test_only_three_earliest_slots_are_offered():
    tz = ZoneInfo("Asia/Beirut")
    tenant = SimpleNamespace(timezone="Asia/Beirut")

    slots = [
        SimpleNamespace(start=datetime(2026, 10, day, 10, tzinfo=tz))
        for day in (24, 21, 23, 22, 20)
    ]

    offered, last_date = select_offered_slots(slots, tenant)

    assert len(offered) == 3
    assert [slot.start.day for slot in offered] == [20, 21, 22]
    assert last_date == "2026-10-22"


def test_next_availability_range_starts_after_last_offered_day():
    tenant = SimpleNamespace(timezone="Asia/Beirut")

    result = next_availability_range(
        tenant,
        "2026-10-22",
    )

    assert result.start.date().isoformat() == "2026-10-23"
    assert result.end.date().isoformat() == "2026-10-30"
