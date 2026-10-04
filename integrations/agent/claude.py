"""Claude-backed conversational agent."""

from anthropic import Anthropic
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from conversations.models import Message
from integrations.agent.base import AgentResponse

# First-pass prompt and tool schemas for Sprint 8 Ticket 1.
# Ticket 2 will refine their behavior and tenant-specific instructions.
SYSTEM_PROMPT = """
You are a booking assistant.

Understand the user's language and intent, including Arabic, English,
French, and mixed-language messages.

Use the available tools when an action is needed.
Use check_availability before attempting to create a booking.
Use ask_clarification when important information is missing.
Do not invent availability or booking information.
""".strip()


TOOLS = [
    {
        "name": "check_availability",
        "description": (
            "Check the tenant's real appointment availability. "
            "Use this when the user wants to book or asks about available times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "create_booking",
        "description": (
            "Create a real booking after the required booking details and "
            "an available slot have been established. Do not call this tool "
            "before availability has been checked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_clarification",
        "description": (
            "Ask the user a clarifying question when required booking "
            "information is missing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The clarification question to ask the user.",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
]


class ClaudeAgent:
    """Use Claude while preserving the shared AgentResponse contract."""

    def __init__(self, client=None):
        if client is not None:
            self.client = client
            return

        if not settings.ANTHROPIC_API_KEY:
            raise ImproperlyConfigured(
                "ANTHROPIC_API_KEY is required when using ClaudeAgent."
            )

        self.client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
        )

    @staticmethod
    def _merge_adjacent_roles(messages):
        """Combine consecutive messages with the same Claude role."""
        merged = []

        for message in messages:
            if merged and merged[-1]["role"] == message["role"]:
                merged[-1]["content"] += "\n" + message["content"]
            else:
                merged.append(dict(message))

        return merged

    def _build_messages(self, conversation, new_messages):
        """Build history plus the newly drained buffer without duplicates."""
        stored_messages = list(
            Message.objects.filter(
                conversation=conversation,
            )
            .exclude(content="")
            .order_by("created_at", "pk")
        )

        history = []

        for message in stored_messages:
            if message.direction == Message.Direction.INBOUND:
                role = "user"
            elif message.direction == Message.Direction.OUTBOUND:
                role = "assistant"
            else:
                continue

            history.append(
                {
                    "role": role,
                    "content": message.content,
                }
            )

        buffered = [
            {
                "role": "user",
                "content": message.content,
            }
            for message in new_messages
            if message.content
        ]

        # WhatsApp inbound messages are persisted before they enter Redis.
        # If the DB already ends with this exact buffered batch, do not append
        # it again or Claude would see the user's latest message twice.
        if buffered:
            already_persisted = (
                len(history) >= len(buffered) and history[-len(buffered) :] == buffered
            )

            if not already_persisted:
                history.extend(buffered)

        return self._merge_adjacent_roles(history)

    def respond(self, conversation, messages):
        """Return a plain reply or tool call as an AgentResponse."""
        claude_messages = self._build_messages(
            conversation=conversation,
            new_messages=messages,
        )

        response = self.client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=claude_messages,
            tools=TOOLS,
        )

        for block in response.content:
            if block.type == "tool_use":
                return AgentResponse(
                    action="tool_call",
                    tool=block.name,
                    tool_args=dict(block.input),
                )

        text_blocks = [
            block.text
            for block in response.content
            if block.type == "text" and block.text
        ]

        if text_blocks:
            return AgentResponse(
                action="reply",
                text="\n".join(text_blocks),
            )

        raise ValueError("Claude returned no supported response content.")
