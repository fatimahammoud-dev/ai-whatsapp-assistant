import logging
import time
from types import SimpleNamespace

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from redis import Redis

from conversations.models import Conversation, Message
from integrations.agent.mock import MockAgent
from integrations.agent.openrouter import OpenRouterAgent
from integrations.booking_flow import (
    clear_pending_state,
    date_range_for_date,
    filter_slots_by_time_preference,
    merge_pending_state,
    parse_slot,
    pending_updates_from_tool,
    resolve_service,
    serialize_slots,
    slot_was_offered,
)
from integrations.tools.booking import SlotUnavailableError
from integrations.tools.dispatcher import dispatch_tool
from integrations.whatsapp import send_text_message

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 5
BUFFER_TTL_SECONDS = 3600

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


def _get_agent():
    """Return the configured conversational agent."""
    if settings.AGENT_BACKEND == "mock":
        return MockAgent()

    if settings.AGENT_BACKEND == "openrouter":
        return OpenRouterAgent()

    raise ImproperlyConfigured(f"Unsupported AGENT_BACKEND: {settings.AGENT_BACKEND!r}")


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
            status__in=[
                Conversation.Status.ACTIVE,
                Conversation.Status.AWAITING_USER,
            ],
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

    response = _get_agent().respond(
        conversation=conversation,
        messages=messages,
    )

    if response.action == "reply":
        send_text_message(
            conversation,
            response.text,
        )
        return

    if response.action != "tool_call":
        return

    logger.info(
        "Agent requested tool call tool=%s tenant_id=%s end_user_id=%s",
        response.tool,
        tenant_id,
        end_user_id,
    )

    tool_args = dict(response.tool_args)
    state_updates = pending_updates_from_tool(
        response.tool,
        tool_args,
    )

    if response.tool == "ask_clarification":
        merge_pending_state(
            conversation,
            state_updates,
            awaiting=True,
        )

        reply_text = dispatch_tool(
            "ask_clarification",
            text=tool_args["text"],
        )

        send_text_message(
            conversation,
            reply_text,
        )
        return

    if response.tool == "check_availability":
        state = merge_pending_state(
            conversation,
            state_updates,
            awaiting=True,
        )

        date_text = tool_args.get("date") or state.get("date")
        time_preference = (
            tool_args.get("time_preference") or state.get("time_preference") or "any"
        )
        service_name = tool_args.get("service_name") or state.get("service_name")

        date_range = (
            date_range_for_date(
                conversation.tenant,
                date_text,
            )
            if date_text
            else None
        )

        service = resolve_service(
            conversation.tenant,
            service_name,
        )

        availability_args = {
            "tenant": conversation.tenant,
            "date_range": date_range,
        }

        if service is not None:
            availability_args["service"] = service

        result = dispatch_tool(
            "check_availability",
            **availability_args,
        )

        result = filter_slots_by_time_preference(
            result,
            conversation.tenant,
            time_preference,
        )

        offered_slots = serialize_slots(result)

        merge_pending_state(
            conversation,
            {
                "offered_slots": offered_slots,
            },
            awaiting=True,
        )

        if result:
            reply_text = "Available appointment times: " + ", ".join(
                slot.start.strftime("%Y-%m-%d %H:%M") for slot in result
            )
        else:
            reply_text = "No appointment times are available for that request."

        send_text_message(
            conversation,
            reply_text,
        )
        return

    if response.tool == "create_booking":
        state = dict(conversation.pending_intent_state or {})

        service_name = tool_args.get("service_name") or state.get("service_name")
        slot_start = tool_args.get("slot_start") or state.get("slot_start")
        slot_end = tool_args.get("slot_end") or state.get("slot_end")

        merge_pending_state(
            conversation,
            state_updates,
            awaiting=True,
        )

        if not service_name or not slot_start or not slot_end:
            reply_text = dispatch_tool(
                "ask_clarification",
                text=(
                    "Please provide the missing service or choose "
                    "one of the available appointment times."
                ),
            )

            send_text_message(
                conversation,
                reply_text,
            )
            return

        service = resolve_service(
            conversation.tenant,
            service_name,
        )

        if service is None:
            reply_text = dispatch_tool(
                "ask_clarification",
                text=(
                    "I could not match that service. "
                    "Please specify the service you want to book."
                ),
            )

            send_text_message(
                conversation,
                reply_text,
            )
            return

        slot = parse_slot(
            conversation.tenant,
            slot_start,
            slot_end,
        )

        if not slot_was_offered(
            slot,
            state.get("offered_slots"),
        ):
            reply_text = dispatch_tool(
                "ask_clarification",
                text=(
                    "Please choose one of the available appointment "
                    "times that was offered."
                ),
            )

            send_text_message(
                conversation,
                reply_text,
            )
            return

        try:
            result = dispatch_tool(
                "create_booking",
                tenant=conversation.tenant,
                end_user=conversation.end_user,
                slot=slot,
                service=service,
            )
        except SlotUnavailableError:
            reply_text = dispatch_tool(
                "ask_clarification",
                text=(
                    "That appointment time is no longer available. "
                    "Please choose another available time."
                ),
            )

            send_text_message(
                conversation,
                reply_text,
            )
            return

        clear_pending_state(conversation)

        send_text_message(
            conversation,
            str(result),
        )
        return

    result = dispatch_tool(
        response.tool,
        **tool_args,
    )

    send_text_message(
        conversation,
        str(result),
    )


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

    concatenated_messages = "\n".join(
        saved_messages[message_id].content
        for message_id in message_ids
        if message_id in saved_messages
    )

    process_buffered_messages(
        tenant_id,
        end_user_id,
        concatenated_messages,
    )
