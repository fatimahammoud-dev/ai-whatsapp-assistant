import logging
import time

from celery import shared_task
from django.conf import settings
from redis import Redis

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5

_DRAIN_BUFFER_SCRIPT = """
local current_timestamp = redis.call("GET", KEYS[2])

if not current_timestamp or current_timestamp ~= ARGV[1] then
    return {}
end

local messages = redis.call("LRANGE", KEYS[1], 0, -1)

redis.call("DEL", KEYS[1])
redis.call("DEL", KEYS[2])

return messages
"""


def _buffer_key(tenant_id, end_user_id):
    return f"whatsapp:buffer:{tenant_id}:{end_user_id}"


def _last_message_key(tenant_id, end_user_id):
    return f"whatsapp:last-message:{tenant_id}:{end_user_id}"


def _redis_client():
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


def process_buffered_messages(
    tenant_id,
    end_user_id,
    concatenated_messages,
):
    """Current processing stub, to be replaced by the real pipeline later."""
    logger.info(
        "Buffered WhatsApp messages ready for processing "
        "tenant_id=%s end_user_id=%s",
        tenant_id,
        end_user_id,
    )


def buffer_inbound_message(
    tenant_id,
    end_user_id,
    message_content,
):
    scheduled_at = time.time_ns()

    client = _redis_client()

    with client.pipeline(transaction=True) as pipeline:
        pipeline.rpush(
            _buffer_key(tenant_id, end_user_id),
            message_content,
        )
        pipeline.set(
            _last_message_key(tenant_id, end_user_id),
            str(scheduled_at),
        )
        pipeline.execute()

    debounce_buffer_task.apply_async(
        args=(tenant_id, end_user_id, scheduled_at),
        countdown=DEBOUNCE_SECONDS,
    )


@shared_task
def debounce_buffer_task(
    tenant_id,
    end_user_id,
    scheduled_at,
):
    client = _redis_client()

    messages = client.eval(
        _DRAIN_BUFFER_SCRIPT,
        2,
        _buffer_key(tenant_id, end_user_id),
        _last_message_key(tenant_id, end_user_id),
        str(scheduled_at),
    )

    if not messages:
        return

    concatenated_messages = "\n".join(messages)

    process_buffered_messages(
        tenant_id,
        end_user_id,
        concatenated_messages,
    )
