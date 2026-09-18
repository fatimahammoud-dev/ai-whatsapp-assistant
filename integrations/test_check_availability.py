from datetime import datetime

from integrations.tools.availability import TimeSlot, check_availability


def test_check_availability_returns_predictable_fake_slots():
    slots = check_availability(
        tenant=object(),
        date_range=object(),
    )

    assert slots == [
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


def test_check_availability_is_independent_of_input():
    first_result = check_availability(
        tenant="tenant-a",
        date_range="range-a",
    )
    second_result = check_availability(
        tenant="tenant-b",
        date_range="range-b",
    )

    assert first_result == second_result
    assert len(first_result) == 3
    assert all(isinstance(slot, TimeSlot) for slot in first_result)
