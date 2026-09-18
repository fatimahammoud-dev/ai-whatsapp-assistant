"""Named tool dispatcher used by the conversational agent pipeline."""

from integrations.tools.availability import check_availability
from integrations.tools.booking import create_booking
from integrations.tools.clarification import ask_clarification

TOOLS = {
    "check_availability": check_availability,
    "create_booking": create_booking,
    "ask_clarification": ask_clarification,
}


def dispatch_tool(tool_name, **tool_args):
    """Execute a registered tool by name."""
    try:
        tool = TOOLS[tool_name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool: {tool_name}") from exc

    return tool(**tool_args)
