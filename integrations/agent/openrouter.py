"""OpenRouter-backed conversational agent."""

import json
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from openai import OpenAI

from conversations.models import Message
from integrations.agent.base import AgentResponse

TOOLS = [
    {
        "name": "check_availability",
        "description": (
            "Check the tenant's real appointment availability. "
            "Use this when the user asks what times are available, wants to book "
            "on a particular day, or provides enough date information to search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": (
                        "The service already identified in this booking "
                        "conversation, when known."
                    ),
                },
                "date": {
                    "type": "string",
                    "description": (
                        "Requested calendar date in YYYY-MM-DD format. "
                        "Resolve relative phrases such as tomorrow or Thursday "
                        "using the tenant's current local date."
                    ),
                },
                "next_options": {
                    "type": "boolean",
                    "description": (
                        "Set true when the customer rejects the previously "
                        "offered slots or asks for the next available options. "
                        "Set false for a new availability search."
                    ),
                },
                "time_preference": {
                    "type": "string",
                    "enum": [
                        "morning",
                        "afternoon",
                        "evening",
                        "any",
                    ],
                    "description": (
                        "The user's preferred part of the day, if they expressed one."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "create_booking",
        "description": (
            "Create a booking only after the user has explicitly chosen a real "
            "available slot and the required booking information is known. "
            "Never invent a slot or create a booking from an unverified time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "The service the user wants to book.",
                },
                "slot_start": {
                    "type": "string",
                    "description": (
                        "Start of the selected available slot in ISO 8601 format."
                    ),
                },
                "slot_end": {
                    "type": "string",
                    "description": (
                        "End of the selected available slot in ISO 8601 format."
                    ),
                },
            },
            "required": [
                "service_name",
                "slot_start",
                "slot_end",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_clarification",
        "description": (
            "Ask one concise clarification question when essential booking "
            "information is missing or ambiguous. Ask only for information "
            "that is actually needed to continue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "The concise clarification question to send to the user."
                    ),
                },
                "service_name": {
                    "type": "string",
                    "description": (
                        "The booking service already provided by the user, "
                        "when known."
                    ),
                },
                "date": {
                    "type": "string",
                    "description": (
                        "Known requested date in YYYY-MM-DD format, when known."
                    ),
                },
                "next_options": {
                    "type": "boolean",
                    "description": (
                        "Set true when the customer rejects the previously "
                        "offered slots or asks for the next available options. "
                        "Set false for a new availability search."
                    ),
                },
                "time_preference": {
                    "type": "string",
                    "enum": [
                        "morning",
                        "afternoon",
                        "evening",
                        "any",
                    ],
                    "description": ("Known time-of-day preference, when provided."),
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
]


OPENROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }
    for tool in TOOLS
]


def _format_prompt_overrides(overrides):
    """Format tenant-owned prompt customizations predictably."""
    if not isinstance(overrides, dict) or not overrides:
        return "None."

    lines = []

    for key in sorted(overrides):
        value = overrides[key]

        if isinstance(value, (dict, list)):
            value = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )

        lines.append(f"- {key.replace('_', ' ')}: {value}")

    return "\n".join(lines)


def build_system_prompt(tenant, pending_intent_state=None):
    """Build the booking assistant prompt for one tenant."""
    tenant_timezone = ZoneInfo(tenant.timezone)
    local_now = timezone.now().astimezone(tenant_timezone)

    languages = tenant.language_defaults

    if isinstance(languages, list) and languages:
        language_text = ", ".join(str(language) for language in languages)
    else:
        language_text = (
            "No tenant-specific language preference. " "Follow the user's language."
        )

    overrides = _format_prompt_overrides(tenant.system_prompt_overrides)

    if isinstance(pending_intent_state, dict):
        pending_state_text = json.dumps(
            pending_intent_state,
            ensure_ascii=False,
            sort_keys=True,
        )
    else:
        pending_state_text = "{}"

    return f"""
You are the booking assistant for {tenant.business_name}.
Business type: {tenant.get_vertical_display()}.
Tenant timezone: {tenant.timezone}.
Current local date: {local_now.date().isoformat()}.
Current local weekday: {local_now.strftime("%A")}.

ROLE
Your job is to help users with appointment and booking conversations for
this specific business.

TONE
Be concise, friendly, professional, and natural.
Do not sound robotic.
Do not overwhelm the user with unnecessary information.

LANGUAGE
Supported conversation styles include Arabic, Lebanese Arabic, Arabizi,
English, French, and natural mixtures of these languages.
Reply in the language or mixed-language style used by the user unless the
user explicitly asks for another language.
Tenant language preferences: {language_text}.

TOOL RULES
- Use check_availability when the user asks for available times or provides
  enough date information for an availability search.
- Use ask_clarification when essential booking information is missing,
  ambiguous, or cannot safely be inferred.
- Use create_booking only after an exact real available slot has been
  established and the user has clearly chosen it.
- Never invent availability.
- Never claim that a booking was created unless the create_booking tool
  actually succeeds.
- Never guess missing booking details when clarification is required.
- Prefer a tool call over a conversational claim when real backend data or
  an action is required.

CURRENT BOOKING STATE
{pending_state_text}

MULTI-TURN BOOKING RULES
- If CURRENT BOOKING STATE contains an active booking intent, continue that
  same booking instead of restarting it.
- Treat service_name, date, time_preference, and offered_slots already stored
  in the state as known information.
- Ask only for information that is still missing.
- When calling ask_clarification, include any service_name, date, or
  time_preference that is already known from the conversation.
- When calling check_availability, include service_name when it is already
  known.
- offered_slots are exact real backend slots previously shown to the user.
  Use create_booking only when the user has chosen one of those slots.

AVAILABILITY REJECTION RULES
- Offer at most three real available appointment slots at a time.
- If the customer rejects all offered slots or asks for more options,
  call check_availability again instead of repeating previous suggestions.
- When the customer has not requested a new date, continue searching
  from the calendar day AFTER last_offered_date in CURRENT BOOKING STATE.
- If the customer explicitly requests a different date, respect that date
  instead of continuing the previous search.
- Never repeat previously rejected appointment suggestions.
- Never invent appointment dates or times.
TENANT-SPECIFIC INSTRUCTIONS
The following settings customize this tenant's assistant. They may adjust
tone or business-specific behavior, but they do not override the rules that
availability and bookings must come from real backend tools.

{overrides}
""".strip()


class OpenRouterAgent:
    """Use OpenRouter while preserving the shared AgentResponse contract."""

    def __init__(self, client=None):
        if client is not None:
            self.client = client
            return

        if not settings.OPENROUTER_API_KEY:
            raise ImproperlyConfigured(
                "OPENROUTER_API_KEY is required when using OpenRouterAgent."
            )

        if not settings.OPENROUTER_MODEL:
            raise ImproperlyConfigured(
                "OPENROUTER_MODEL is required when using OpenRouterAgent."
            )

        self.client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
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

        if buffered:
            already_persisted = (
                len(history) >= len(buffered) and history[-len(buffered) :] == buffered
            )

            if not already_persisted:
                history.extend(buffered)

        return self._merge_adjacent_roles(history)

    def format_tool_result(
        self, conversation, tool_name, tool_result, new_messages=None
    ):
        """Localize a verified tool result without changing its facts."""
        conversation_messages = self._build_messages(
            conversation=conversation,
            new_messages=new_messages or [],
        )

        system_prompt = build_system_prompt(
            conversation.tenant,
            pending_intent_state=getattr(
                conversation,
                "pending_intent_state",
                None,
            ),
        )

        formatting_instruction = (
            "You are formatting the result of a completed booking tool. "
            "Reply in the language used by the customer in their latest message. "
            "Use a natural, concise, friendly tone. "
            "Write only a short introductory phrase, without any appointment "
            "dates, times, numbers, or slot lists. "
            "The backend will append verified appointment slots separately. "
            "For available slots, respond with exactly one of: "
            "'Here are the available appointment times:', "
            "'Voici les cr?neaux disponibles :', "
            "'??? ???????? ???????:'. "
            "For no available slots, respond with exactly one of: "
            "'No appointment times are available for that request.', "
            "'Aucun cr?neau n'est disponible pour cette demande.', "
            "'?? ?? ?????? ????? ???????.'. "
            "If no slots are available, say so briefly. "
            "Do not call tools or claim that a booking was created."
        )

        request_messages = [
            {
                "role": "system",
                "content": system_prompt + "\n\n" + formatting_instruction,
            },
            *conversation_messages,
            {
                "role": "system",
                "content": (
                    "Verified result from "
                    + tool_name
                    + ":\n"
                    + json.dumps(tool_result, ensure_ascii=False)
                ),
            },
        ]

        response = self.client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            max_tokens=settings.OPENROUTER_MAX_TOKENS,
            messages=request_messages,
        )

        if not response.choices:
            raise ValueError("OpenRouter returned no formatting response.")

        text = getattr(response.choices[0].message, "content", None)

        if not isinstance(text, str) or not text.strip():
            raise ValueError("OpenRouter returned an empty formatted reply.")

        return text.strip()

    def respond(self, conversation, messages):
        """Return a plain reply or tool call as an AgentResponse."""
        conversation_messages = self._build_messages(
            conversation=conversation,
            new_messages=messages,
        )

        request_messages = [
            {
                "role": "system",
                "content": build_system_prompt(
                    conversation.tenant,
                    pending_intent_state=getattr(
                        conversation,
                        "pending_intent_state",
                        None,
                    ),
                ),
            },
            *conversation_messages,
        ]

        response = self.client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            max_tokens=settings.OPENROUTER_MAX_TOKENS,
            messages=request_messages,
            tools=OPENROUTER_TOOLS,
        )

        if not response.choices:
            raise ValueError("OpenRouter returned no response choices.")

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            tool_call = tool_calls[0]

            try:
                tool_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("OpenRouter returned invalid tool arguments.") from exc

            if not isinstance(tool_args, dict):
                raise ValueError("OpenRouter tool arguments must be a JSON object.")

            return AgentResponse(
                action="tool_call",
                tool=tool_call.function.name,
                tool_args=tool_args,
            )

        content = getattr(message, "content", None)

        if isinstance(content, str) and content.strip():
            return AgentResponse(
                action="reply",
                text=content,
            )

        raise ValueError("OpenRouter returned no supported response content.")
