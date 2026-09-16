from unittest.mock import Mock

import pytest

from integrations.tasks import (
    DEBOUNCE_SECONDS,
    _buffer_key,
    _last_message_key,
    _redis_client,
    buffer_inbound_message,
    debounce_buffer_task,
)

TENANT_ID = 900001
END_USER_ID = 900002


@pytest.fixture
def redis_client():
    client = _redis_client()

    keys = (
        _buffer_key(TENANT_ID, END_USER_ID),
        _last_message_key(TENANT_ID, END_USER_ID),
    )

    client.delete(*keys)

    yield client

    client.delete(*keys)


def test_three_rapid_messages_trigger_processing_once(
    monkeypatch,
    redis_client,
):
    timestamps = iter(
        [
            1_000_000_000,
            2_000_000_000,
            3_000_000_000,
        ]
    )

    monkeypatch.setattr(
        "integrations.tasks.time.time_ns",
        lambda: next(timestamps),
    )

    scheduled_tasks = []

    def capture_apply_async(*, args, countdown):
        scheduled_tasks.append(
            (
                args,
                countdown,
            )
        )

    monkeypatch.setattr(
        debounce_buffer_task,
        "apply_async",
        capture_apply_async,
    )

    process_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.process_buffered_messages",
        process_mock,
    )

    buffer_inbound_message(
        TENANT_ID,
        END_USER_ID,
        "First message",
    )
    buffer_inbound_message(
        TENANT_ID,
        END_USER_ID,
        "Second message",
    )
    buffer_inbound_message(
        TENANT_ID,
        END_USER_ID,
        "Third message",
    )

    assert len(scheduled_tasks) == 3

    assert all(countdown == DEBOUNCE_SECONDS for _, countdown in scheduled_tasks)

    for args, _ in scheduled_tasks:
        debounce_buffer_task.run(*args)

    process_mock.assert_called_once_with(
        TENANT_ID,
        END_USER_ID,
        "First message\nSecond message\nThird message",
    )
