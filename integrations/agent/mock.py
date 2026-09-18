"""Simple deterministic agent used to exercise the conversation pipeline."""

from integrations.agent.base import AgentResponse


class MockAgent:
    """Return predictable responses without calling a real LLM."""

    BOOKING_KEYWORDS = ("book", "appointment", "rendez-vous")

    def respond(self, conversation, messages):
        """Return a canned reply or a booking availability tool call."""
        del conversation

        combined_text = " ".join(message.content for message in messages).lower()

        if any(keyword in combined_text for keyword in self.BOOKING_KEYWORDS):
            return AgentResponse(
                action="tool_call",
                tool="check_availability",
                tool_args={},
            )

        return AgentResponse(
            action="reply",
            text="Thanks for your message. How can I help?",
        )
