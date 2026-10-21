from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from integrations.tools import booking


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 1, 15, 10), datetime(2026, 1, 15, 10)),
        (datetime(2026, 1, 15, 11), datetime(2026, 1, 15, 10)),
    ],
)
def test_invalid_booking_slot_rejected_before_database(monkeypatch, start, end):
    create = Mock()
    monkeypatch.setattr(booking.Booking.objects, "create", create)

    slot = SimpleNamespace(start=start, end=end)

    with pytest.raises(
        ValueError,
        match="A booking slot must end after it starts",
    ):
        booking.create_booking(
            tenant=object(),
            end_user=object(),
            slot=slot,
            service=object(),
        )

    create.assert_not_called()
