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
def test_rejection_searches_after_last_offered_day(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Pagination Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="pagination-test-phone",
        whatsapp_access_token=b"test-token",
    )
    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000001",
    )
    Conversation.objects.create(
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

    captured = {}

    def fake_dispatch(name, **kwargs):
        if name == "check_availability":
            captured["range"] = kwargs["date_range"]
            return []
        raise AssertionError(f"Unexpected tool: {name}")

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr("integrations.tasks.dispatch_tool", fake_dispatch)
    monkeypatch.setattr("integrations.tasks.send_text_message", Mock())

    process_buffered_messages(tenant.pk, user.pk, "Other options?")

    assert captured["range"].start.date().isoformat() == "2026-10-23"
    assert captured["range"].end.date().isoformat() == "2026-10-30"


@pytest.mark.django_db
def test_explicit_date_overrides_next_options(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Explicit Date Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="explicit-date-phone",
        whatsapp_access_token=b"test-token",
    )
    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000002",
    )
    Conversation.objects.create(
        tenant=tenant,
        end_user=user,
        status=Conversation.Status.AWAITING_USER,
        pending_intent_state={
            "intent": "booking",
            "last_offered_date": "2026-10-22",
        },
    )

    agent = Mock()
    agent.respond.return_value = AgentResponse(
        action="tool_call",
        tool="check_availability",
        tool_args={
            "next_options": True,
            "date": "2026-11-05",
        },
    )

    captured = {}

    def fake_dispatch(name, **kwargs):
        if name == "check_availability":
            captured["range"] = kwargs["date_range"]
            return []
        raise AssertionError(f"Unexpected tool: {name}")

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr("integrations.tasks.dispatch_tool", fake_dispatch)
    monkeypatch.setattr("integrations.tasks.send_text_message", Mock())

    process_buffered_messages(tenant.pk, user.pk, "November 5 instead")

    assert captured["range"].start.date().isoformat() == "2026-11-05"
    assert captured["range"].end.date().isoformat() == "2026-11-06"


@pytest.mark.django_db
def test_empty_availability_clears_old_slots(monkeypatch):
    tenant = Tenant.objects.create(
        business_name="Empty Availability Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="empty-availability-phone",
        whatsapp_access_token=b"test-token",
    )

    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000003",
    )

    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=user,
        status=Conversation.Status.AWAITING_USER,
        pending_intent_state={
            "intent": "booking",
            "last_offered_date": "2026-10-22",
            "offered_slots": [
                {
                    "start": "2026-10-22T10:00:00+03:00",
                    "end": "2026-10-22T10:30:00+03:00",
                }
            ],
        },
    )

    agent = Mock()
    agent.respond.return_value = AgentResponse(
        action="tool_call",
        tool="check_availability",
        tool_args={"next_options": True},
    )

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr(
        "integrations.tasks.dispatch_tool",
        lambda name, **kwargs: [],
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        Mock(),
    )

    process_buffered_messages(
        tenant.pk,
        user.pk,
        "Other available times?",
    )

    conversation.refresh_from_db()
    state = conversation.pending_intent_state

    assert state["offered_slots"] == []
    assert state["last_offered_date"] is None


@pytest.mark.django_db
def test_formatter_failure_uses_backend_fallback(monkeypatch, settings):
    tenant = Tenant.objects.create(
        business_name="Formatter Fallback Test",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="formatter-fallback-phone",
        whatsapp_access_token=b"test-token",
    )

    user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170000004",
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

    available_slot = SimpleNamespace(
        start=datetime(2026, 10, 20, 10, 0, tzinfo=tz),
        end=datetime(2026, 10, 20, 10, 30, tzinfo=tz),
    )

    send_mock = Mock()

    monkeypatch.setattr("integrations.tasks._get_agent", lambda: agent)
    monkeypatch.setattr(
        "integrations.tasks.dispatch_tool",
        lambda name, **kwargs: [available_slot],
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    def failing_formatter(*args, **kwargs):
        raise RuntimeError("Simulated formatter failure")

    monkeypatch.setattr(
        "integrations.tasks.OpenRouterAgent.format_tool_result",
        failing_formatter,
    )

    settings.AGENT_BACKEND = "openrouter"
    settings.OPENROUTER_API_KEY = "test-only-key"
    settings.OPENROUTER_MODEL = "test/model"

    process_buffered_messages(
        tenant.pk,
        user.pk,
        "Available appointments?",
    )

    assert send_mock.call_count == 1

    sent_text = send_mock.call_args.args[1]

    assert "2026-10-20 10:00" in sent_text
