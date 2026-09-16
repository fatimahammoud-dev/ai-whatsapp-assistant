from concurrent.futures import ThreadPoolExecutor
from threading import Lock
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


def test_messages_after_debounce_window_process_separately(
    monkeypatch,
    redis_client,
):
    timestamps = iter(
        [
            10_000_000_000,
            20_000_000_000,
        ]
    )

    monkeypatch.setattr(
        "integrations.tasks.time.time_ns",
        lambda: next(timestamps),
    )

    scheduled_tasks = []

    def capture_apply_async(*, args, countdown):
        scheduled_tasks.append(args)

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
        "First batch",
    )

    debounce_buffer_task.run(*scheduled_tasks[0])

    buffer_inbound_message(
        TENANT_ID,
        END_USER_ID,
        "Second batch",
    )

    debounce_buffer_task.run(*scheduled_tasks[1])

    assert process_mock.call_count == 2

    assert process_mock.call_args_list[0].args == (
        TENANT_ID,
        END_USER_ID,
        "First batch",
    )

    assert process_mock.call_args_list[1].args == (
        TENANT_ID,
        END_USER_ID,
        "Second batch",
    )


def test_buffer_is_cleared_after_processing(
    monkeypatch,
    redis_client,
):
    monkeypatch.setattr(
        "integrations.tasks.time.time_ns",
        lambda: 30_000_000_000,
    )

    scheduled_tasks = []

    monkeypatch.setattr(
        debounce_buffer_task,
        "apply_async",
        lambda *, args, countdown: scheduled_tasks.append(args),
    )

    process_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks.process_buffered_messages",
        process_mock,
    )

    buffer_inbound_message(
        TENANT_ID,
        END_USER_ID,
        "Message to drain",
    )

    debounce_buffer_task.run(*scheduled_tasks[0])

    assert (
        redis_client.exists(
            _buffer_key(TENANT_ID, END_USER_ID),
        )
        == 0
    )

    assert (
        redis_client.exists(
            _last_message_key(TENANT_ID, END_USER_ID),
        )
        == 0
    )

    debounce_buffer_task.run(*scheduled_tasks[0])

    process_mock.assert_called_once_with(
        TENANT_ID,
        END_USER_ID,
        "Message to drain",
    )


def test_near_simultaneous_messages_are_not_dropped_or_duplicated(
    monkeypatch,
    redis_client,
):
    next_timestamp = 40_000_000_000
    timestamp_lock = Lock()

    def unique_timestamp():
        nonlocal next_timestamp

        with timestamp_lock:
            next_timestamp += 1
            return next_timestamp

    monkeypatch.setattr(
        "integrations.tasks.time.time_ns",
        unique_timestamp,
    )

    scheduled_tasks = []
    schedule_lock = Lock()

    def capture_apply_async(*, args, countdown):
        with schedule_lock:
            scheduled_tasks.append(args)

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

    messages = [
        "Concurrent message A",
        "Concurrent message B",
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                buffer_inbound_message,
                TENANT_ID,
                END_USER_ID,
                message,
            )
            for message in messages
        ]

        for future in futures:
            future.result()

    for args in scheduled_tasks:
        debounce_buffer_task.run(*args)

    assert process_mock.call_count == 1

    processed_text = process_mock.call_args.args[2]
    processed_messages = processed_text.split("\n")

    assert sorted(processed_messages) == sorted(messages)
    assert len(processed_messages) == len(messages)
