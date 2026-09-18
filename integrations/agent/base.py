"""Shared response contract for conversational agents."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class AgentResponse:
    """Represent an agent decision for the conversation pipeline.

    The response has one of two shapes:

    - Plain reply:
      action="reply" with text containing the message to send.

    - Tool call:
      action="tool_call" with tool naming the tool to execute and
      tool_args containing the arguments for that tool.

    This contract is independent of any specific agent implementation so
    both the MockAgent and a future real LLM agent can use the same pipeline.
    """

    action: Literal["reply", "tool_call"]
    text: str | None = None
    tool: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
