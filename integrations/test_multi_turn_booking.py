from unittest.mock import Mock

import pytest

from bookings.models import Booking, Service
from conversations.models import Conversation, EndUser
from integrations.agent.base import AgentResponse
from integrations.tasks import process_buffered_messages
from integrations.views import _resolve_whatsapp_context
from tenants.models import Tenant


def _tenant():
    return Tenant.objects.create(
        business_name="Multi Turn Clinic",
        vertical=Tenant.Vertical.DOCTOR,
        timezone="Asia/Beirut",
        phone_number_id="multi-turn-phone-id",
        whatsapp_access_token=b"multi-turn-token",
    )


def _whatsapp_payload(
    tenant,
    phone_number,
    message_id="wamid.multi-turn",
    text="Next message",
):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": tenant.phone_number_id,
                            },
                            "messages": [
                                {
                                    "from": phone_number,
                                    "id": message_id,
                                    "type": "text",
                                    "text": {
                                        "body": text,
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


@pytest.mark.django_db
def test_whatsapp_reuses_awaiting_user_conversation():
    tenant = _tenant()

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170111111",
    )

    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.AWAITING_USER,
        pending_intent_state={
            "intent": "booking",
            "service_name": "Consultation",
        },
    )

    resolved = _resolve_whatsapp_context(
        _whatsapp_payload(
            tenant,
            end_user.phone_number,
        )
    )

    assert resolved["conversation"].pk == conversation.pk
    assert (
        Conversation.objects.filter(
            tenant=tenant,
            end_user=end_user,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_three_turn_booking_flow_persists_and_clears_state(
    monkeypatch,
):
    tenant = _tenant()

    service = Service.objects.create(
        tenant=tenant,
        name="Consultation",
        duration_minutes=30,
        is_active=True,
    )

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="96170222222",
    )

    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    class MultiTurnAgent:
        def __init__(self):
            self.turn = 0

        def respond(self, conversation, messages):
            self.turn += 1

            if self.turn == 1:
                return AgentResponse(
                    action="tool_call",
                    tool="ask_clarification",
                    tool_args={
                        "text": "Which day would you prefer?",
                        "service_name": "Consultation",
                    },
                )

            if self.turn == 2:
                return AgentResponse(
                    action="tool_call",
                    tool="check_availability",
                    tool_args={
                        "date": "2026-10-12",
                        "time_preference": "afternoon",
                    },
                )

            offered = conversation.pending_intent_state["offered_slots"][0]

            return AgentResponse(
                action="tool_call",
                tool="create_booking",
                tool_args={
                    "service_name": "Consultation",
                    "slot_start": offered["start"],
                    "slot_end": offered["end"],
                },
            )

    agent = MultiTurnAgent()
    send_mock = Mock()

    monkeypatch.setattr(
        "integrations.tasks._get_agent",
        lambda: agent,
    )
    monkeypatch.setattr(
        "integrations.tasks.send_text_message",
        send_mock,
    )

    # Turn 1: service is known, date/time still missing.
    process_buffered_messages(
        tenant_id=tenant.pk,
        end_user_id=end_user.pk,
        concatenated_messages="I want a Consultation",
    )

    conversation.refresh_from_db()

    assert conversation.status == Conversation.Status.AWAITING_USER
    assert conversation.pending_intent_state == {
        "intent": "booking",
        "service_name": "Consultation",
    }

    # Turn 2: user supplies date/time preference.
    process_buffered_messages(
        tenant_id=tenant.pk,
        end_user_id=end_user.pk,
        concatenated_messages="Monday afternoon",
    )

    conversation.refresh_from_db()

    state = conversation.pending_intent_state

    assert conversation.status == Conversation.Status.AWAITING_USER
    assert state["intent"] == "booking"
    assert state["service_name"] == "Consultation"
    assert state["date"] == "2026-10-12"
    assert state["time_preference"] == "afternoon"
    assert state["offered_slots"]

    # Turn 3: user chooses one exact real slot.
    process_buffered_messages(
        tenant_id=tenant.pk,
        end_user_id=end_user.pk,
        concatenated_messages="The first one works",
    )

    conversation.refresh_from_db()

    booking = Booking.objects.get(
        tenant=tenant,
        end_user=end_user,
    )

    assert booking.service == service
    assert booking.status == Booking.Status.CONFIRMED

    assert conversation.status == Conversation.Status.ACTIVE
    assert conversation.pending_intent_state == {}

    assert send_mock.call_count == 3
