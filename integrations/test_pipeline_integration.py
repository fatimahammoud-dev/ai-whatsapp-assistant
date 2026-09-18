from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from conversations.models import Conversation, EndUser, Message
from integrations.tasks import process_buffered_messages
from integrations.tools.availability import TimeSlot
from tenants.models import Tenant

RECIPIENT = "96170123456"


@pytest.mark.django_db
def test_booking_message_runs_full_mock_agent_pipeline_without_network():
    tenant = Tenant.objects.create(
        business_name="Pipeline Integration Test",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id="pipeline-test-phone-id",
        whatsapp_access_token=b"pipeline-test-token",
    )

    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number=RECIPIENT,
    )

    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=Conversation.Status.ACTIVE,
    )

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="I want to book an appointment",
        whatsapp_message_id="wamid.pipeline-inbound",
    )

    slots = [
        TimeSlot(
            start=datetime(2026, 1, 15, 9, 0),
            end=datetime(2026, 1, 15, 9, 30),
        ),
        TimeSlot(
            start=datetime(2026, 1, 15, 11, 0),
            end=datetime(2026, 1, 15, 11, 30),
        ),
    ]

    availability_mock = Mock(return_value=slots)

    with (
        patch.dict(
            "integrations.tools.dispatcher.TOOLS",
            {"check_availability": availability_mock},
        ),
        patch("integrations.whatsapp.urlopen") as urlopen_mock,
    ):
        response = urlopen_mock.return_value
        response.__enter__.return_value.getcode.return_value = 200

        process_buffered_messages(
            tenant_id=tenant.pk,
            end_user_id=end_user.pk,
            concatenated_messages="I want to book an appointment",
        )

    availability_mock.assert_called_once_with(
        tenant=tenant,
        date_range=None,
    )

    urlopen_mock.assert_called_once()

    outbound = Message.objects.get(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
    )

    assert "Available appointment times:" in outbound.content
    assert "2026-01-15 09:00" in outbound.content
    assert "2026-01-15 11:00" in outbound.content
