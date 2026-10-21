"""Named tool dispatcher and customer-facing reply formatting."""

from integrations.tools.availability import check_availability
from integrations.tools.booking import create_booking
from integrations.tools.clarification import ask_clarification

TOOLS = {
    "check_availability": check_availability,
    "create_booking": create_booking,
    "ask_clarification": ask_clarification,
}

CONTEXT_ARGS = {
    "check_availability": ("tenant",),
    "create_booking": ("tenant", "end_user"),
    "ask_clarification": (),
}


def _format_slots(slots):
    if not slots:
        return "Sorry, there are no available appointment times right now."

    return "Available appointment times: " + ", ".join(
        slot.start.strftime("%Y-%m-%d %H:%M") for slot in slots
    )


def _format_booking(booking):
    return (
        "Your appointment has been booked successfully for "
        f"{booking.scheduled_start:%Y-%m-%d %H:%M}."
    )


def _format_clarification(text):
    return text


REPLY_FORMATTERS = {
    "check_availability": _format_slots,
    "create_booking": _format_booking,
    "ask_clarification": _format_clarification,
}


def dispatch_tool(tool_name, **tool_args):
    """Execute a registered tool by name."""
    try:
        tool = TOOLS[tool_name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool: {tool_name}") from exc

    return tool(**tool_args)


def run_tool(tool_name, tool_args, conversation):
    """Run a tool with trusted conversation context and format its reply."""
    if tool_name not in TOOLS:
        raise ValueError(f"Unknown tool: {tool_name}")

    args = dict(tool_args or {})

    for context_arg in CONTEXT_ARGS[tool_name]:
        args[context_arg] = getattr(conversation, context_arg)

    if tool_name == "check_availability":
        args.setdefault("date_range", None)

    result = dispatch_tool(tool_name, **args)
    return REPLY_FORMATTERS[tool_name](result)
