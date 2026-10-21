from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from integrations.tools import dispatcher


@pytest.fixture
def conversation():
    return SimpleNamespace(
        tenant=object(),
        end_user=object(),
    )


def test_every_tool_has_context_and_formatter():
    assert set(dispatcher.TOOLS) == set(dispatcher.CONTEXT_ARGS)
    assert set(dispatcher.TOOLS) == set(dispatcher.REPLY_FORMATTERS)


def test_empty_availability_has_clear_reply(monkeypatch, conversation):
    tool = Mock(return_value=[])
    monkeypatch.setitem(dispatcher.TOOLS, "check_availability", tool)

    reply = dispatcher.run_tool("check_availability", {}, conversation)

    assert reply == "Sorry, there are no available appointment times right now."
    tool.assert_called_once_with(tenant=conversation.tenant, date_range=None)


def test_booking_reply_does_not_expose_model_representation(monkeypatch, conversation):
    booking = SimpleNamespace(
        scheduled_start=datetime(2026, 1, 15, 9, 0),
    )
    tool = Mock(return_value=booking)
    monkeypatch.setitem(dispatcher.TOOLS, "create_booking", tool)

    slot = object()
    service = object()

    reply = dispatcher.run_tool(
        "create_booking",
        {"slot": slot, "service": service},
        conversation,
    )

    assert reply == (
        "Your appointment has been booked successfully for 2026-01-15 09:00."
    )
    assert "Booking(" not in reply
    tool.assert_called_once_with(
        tenant=conversation.tenant,
        end_user=conversation.end_user,
        slot=slot,
        service=service,
    )


def test_clarification_text_is_preserved(monkeypatch, conversation):
    tool = Mock(return_value="Which day would you prefer?")
    monkeypatch.setitem(dispatcher.TOOLS, "ask_clarification", tool)

    reply = dispatcher.run_tool(
        "ask_clarification",
        {"text": "Which day would you prefer?"},
        conversation,
    )

    assert reply == "Which day would you prefer?"


def test_unknown_tool_is_rejected(conversation):
    with pytest.raises(ValueError, match="Unknown tool"):
        dispatcher.run_tool("not_registered", {}, conversation)


def test_agent_cannot_override_tenant_context(monkeypatch, conversation):
    tool = Mock(return_value=[])
    monkeypatch.setitem(dispatcher.TOOLS, "check_availability", tool)

    dispatcher.run_tool(
        "check_availability",
        {"tenant": object()},
        conversation,
    )

    assert tool.call_args.kwargs["tenant"] is conversation.tenant
