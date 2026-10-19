"""Bounded retry helper for transient external-service failures."""

import logging
import random
import time

logger = logging.getLogger(__name__)


def retry_call(
    operation,
    *,
    should_retry,
    attempts=3,
    base_delay=0.25,
    max_delay=2.0,
    sleep=time.sleep,
    random_value=random.random,
    operation_name="external_request",
):
    """Retry transient failures with bounded exponential backoff and jitter."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if not should_retry(exc) or attempt >= attempts:
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay *= 0.5 + random_value() * 0.5

            logger.warning(
                "Retrying external operation=%s attempt=%s/%s error_type=%s",
                operation_name,
                attempt,
                attempts,
                type(exc).__name__,
            )

            sleep(delay)
