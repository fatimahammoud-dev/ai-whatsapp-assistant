import pytest

from integrations.retry import retry_call


class TemporaryFailure(Exception):
    pass


class PermanentFailure(Exception):
    pass


def test_retry_succeeds_after_temporary_failures():
    calls = []
    delays = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise TemporaryFailure()
        return "success"

    result = retry_call(
        operation,
        should_retry=lambda exc: isinstance(exc, TemporaryFailure),
        attempts=3,
        base_delay=1,
        max_delay=2,
        sleep=delays.append,
        random_value=lambda: 0,
    )

    assert result == "success"
    assert len(calls) == 3
    assert delays == [0.5, 1.0]


def test_permanent_error_is_not_retried():
    calls = []

    def operation():
        calls.append(1)
        raise PermanentFailure()

    with pytest.raises(PermanentFailure):
        retry_call(
            operation,
            should_retry=lambda exc: isinstance(exc, TemporaryFailure),
            sleep=lambda _: None,
        )

    assert len(calls) == 1


def test_retry_stops_after_maximum_attempts():
    calls = []

    def operation():
        calls.append(1)
        raise TemporaryFailure()

    with pytest.raises(TemporaryFailure):
        retry_call(
            operation,
            should_retry=lambda exc: isinstance(exc, TemporaryFailure),
            attempts=3,
            sleep=lambda _: None,
        )

    assert len(calls) == 3


def test_retry_rejects_zero_attempts():
    with pytest.raises(ValueError, match="attempts"):
        retry_call(
            lambda: None,
            should_retry=lambda exc: True,
            attempts=0,
        )
