import logging
import time
from types import SimpleNamespace

from celery import shared_task
from django.conf import settings
from redis import Redis

from conversations.models import Conversation
from integrations.agent.mock import MockAgent
from integrations.whatsapp import send_text_message

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
    """Process one drained message batch through the conversational agent."""
    conversation = (
        Conversation.objects.select_related("tenant", "end_user")
        .filter(
            tenant_id=tenant_id,
            end_user_id=end_user_id,
            status=Conversation.Status.ACTIVE,
        )
        .order_by("-started_at")
        .first()
    )

    if conversation is None:
        logger.error(
            "Cannot process buffered messages: no active conversation "
            "tenant_id=%s end_user_id=%s",
            tenant_id,
            end_user_id,
        )
        return

    messages = [
        SimpleNamespace(content=content)
        for content in concatenated_messages.split("\n")
        if content
    ]

    response = MockAgent().respond(
        conversation=conversation,
        messages=messages,
    )

    if response.action == "reply":
        send_text_message(
            conversation.tenant,
            conversation.end_user.phone_number,
            response.text,
        )
        return

    if response.action == "tool_call":
        logger.info(
            "Agent requested tool call tool=%s tenant_id=%s end_user_id=%s",
            response.tool,
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
