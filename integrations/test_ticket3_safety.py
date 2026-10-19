from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from conversations.models import Conversation, EndUser
from integrations.agent.base import AgentResponse
from integrations.tasks import process_buffered_messages
from tenants.models import Tenant


@pytest.mark.django_db
def test_repeated_empty_search_moves_forward(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Cursor Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="cursor-test-phone",
        whatsapp_access_token=b"test-token",
    )
    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000991",
    )
    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=user,
        status=Conversation.Status.AWAITING_USER,
        pending_intent_state={
            "intent": "booking",
            "last_offered_date": "2026-10-22",
            "offered_slots": [],
        },
    )

    agent = Mock()
    agent.respond.return_value = AgentResponse(
        action="tool_call",
        tool="check_availability",
        tool_args={"next_options": True},
    )
    ranges = []

    def fake_dispatch(name, **kwargs):
        assert name == "check_availability"
        ranges.append(kwargs["date_range"])
        return []

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr("integrations.tasks.dispatch_tool", fake_dispatch)
    monkeypatch.setattr("integrations.tasks.send_text_message", Mock())

    process_buffered_messages(tenant.pk, user.pk, "Other options?")
    process_buffered_messages(tenant.pk, user.pk, "Any more?")

    assert len(ranges) == 2
    assert ranges[0].start.date().isoformat() == "2026-10-23"
    assert ranges[1].start.date().isoformat() == "2026-10-30"

    conversation.refresh_from_db()
    assert conversation.pending_intent_state["offered_slots"] == []
    assert conversation.pending_intent_state["last_offered_date"] is None
    assert conversation.pending_intent_state["search_cursor_date"] == "2026-11-05"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "untrusted_intro",
    [
        "Tomorrow afternoon is also available.",
        "You can book next Friday at noon.",
        "2026-12-25 17:00 is available.",
    ],
)
def test_untrusted_ai_intro_never_reaches_customer(
    monkeypatch, settings, untrusted_intro
):
    tenant = Tenant.objects.create(
        business_name="Safe Reply Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="safe-reply-test-phone",
        whatsapp_access_token=b"test-token",
    )
    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000992",
    )
    Conversation.objects.create(
        tenant=tenant,
        end_user=user,
        status=Conversation.Status.ACTIVE,
    )

    agent = Mock()
    agent.respond.return_value = AgentResponse(
        action="tool_call",
        tool="check_availability",
        tool_args={"date": "2026-10-20"},
    )

    tz = ZoneInfo("Asia/Beirut")
    slot = SimpleNamespace(
        start=datetime(2026, 10, 20, 10, 0, tzinfo=tz),
        end=datetime(2026, 10, 20, 10, 30, tzinfo=tz),
    )
    sent = Mock()

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr(
        "integrations.tasks.dispatch_tool",
        lambda name, **kwargs: [slot],
    )
    monkeypatch.setattr("integrations.tasks.send_text_message", sent)
    monkeypatch.setattr(
        "integrations.tasks.OpenRouterAgent.format_tool_result",
        lambda *args, **kwargs: untrusted_intro,
    )

    settings.AGENT_BACKEND = "openrouter"
    settings.OPENROUTER_API_KEY = "test-only-key"
    settings.OPENROUTER_MODEL = "test/model"

    process_buffered_messages(tenant.pk, user.pk, "Available appointments?")

    reply = sent.call_args.args[1]
    assert "2026-10-20 10:00" in reply
    assert untrusted_intro not in reply
