import logging
import time

from celery import shared_task
from django.conf import settings
from redis import Redis

from conversations.models import Conversation, Message
from integrations.agent.mock import MockAgent
from integrations.tools.dispatcher import run_tool
from integrations.whatsapp import send_text_message

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5
BUFFER_TTL_SECONDS = 3600
FALLBACK_REPLY = (
    "Sorry, something went wrong on our side. Please try again in a moment."
)

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
    messages,
):
    """Process one drained message batch through the conversational agent."""
    if not messages:
        logger.warning(
            "Cannot process empty message batch tenant_id=%s end_user_id=%s",
            tenant_id,
            end_user_id,
        )
        return

    conversation = messages[-1].conversation

    if (
        conversation is None
        or conversation.tenant_id != tenant_id
        or conversation.end_user_id != end_user_id
        or conversation.status != Conversation.Status.ACTIVE
        or any(message.conversation_id != conversation.pk for message in messages)
    ):
        logger.warning(
            "Cannot process inactive or mismatched conversation "
            "tenant_id=%s end_user_id=%s",
            tenant_id,
            end_user_id,
        )
        return

    try:
        response = MockAgent().respond(
            conversation=conversation,
            messages=messages,
        )

        if response.action == "reply":
            send_text_message(
                conversation,
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

            reply_text = run_tool(
                response.tool,
                response.tool_args,
                conversation,
            )

            send_text_message(
                conversation,
                reply_text,
            )
            return

        logger.error(
            "Unsupported agent action=%s tenant_id=%s end_user_id=%s",
            response.action,
            tenant_id,
            end_user_id,
        )
    except Exception:
        logger.exception(
            "Agent/tool processing failed tenant_id=%s end_user_id=%s",
            tenant_id,
            end_user_id,
        )

    send_text_message(conversation, FALLBACK_REPLY)


def buffer_inbound_message(
    tenant_id,
    end_user_id,
    message_id,
):
    scheduled_at = time.time_ns()

    client = _redis_client()

    with client.pipeline(transaction=True) as pipeline:
        pipeline.rpush(
            _buffer_key(tenant_id, end_user_id),
            str(message_id),
        )
        pipeline.set(
            _last_message_key(tenant_id, end_user_id),
            str(scheduled_at),
        )
        pipeline.expire(
            _buffer_key(tenant_id, end_user_id),
            BUFFER_TTL_SECONDS,
        )
        pipeline.expire(
            _last_message_key(tenant_id, end_user_id),
            BUFFER_TTL_SECONDS,
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

    message_ids = [int(raw_id) for raw_id in messages]
    saved_messages = Message.objects.in_bulk(message_ids)

    batch = [
        saved_messages[message_id]
        for message_id in message_ids
        if message_id in saved_messages
    ]

    if not batch:
        return

    process_buffered_messages(
        tenant_id,
        end_user_id,
        batch,
    )
