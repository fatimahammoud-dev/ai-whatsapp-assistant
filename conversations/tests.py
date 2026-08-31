# Create your tests here.
import pytest
from django.db import IntegrityError, transaction

from conversations.models import Conversation, EndUser, Message
from tenants.models import Tenant


@pytest.mark.django_db
def test_end_user_phone_number_is_unique_per_tenant():
    tenant_a = Tenant.objects.create(
        business_name="Tenant A",
        vertical="doctor",
    )
    tenant_b = Tenant.objects.create(
        business_name="Tenant B",
        vertical="doctor",
    )

    EndUser.objects.create(
        tenant=tenant_a,
        phone_number="+96170123456",
    )

    EndUser.objects.create(
        tenant=tenant_b,
        phone_number="+96170123456",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EndUser.objects.create(
                tenant=tenant_a,
                phone_number="+96170123456",
            )


@pytest.mark.django_db
def test_conversation_messages_are_ordered_and_whatsapp_id_is_unique():
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number="+96170123456",
    )
    conversation = Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
    )

    first_message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hello",
        whatsapp_message_id="wamid.1",
    )
    second_message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
        message_type=Message.MessageType.TEXT,
        content="Hi, how can I help?",
        whatsapp_message_id="wamid.2",
    )

    assert list(conversation.message_set.all()) == [
        first_message,
        second_message,
    ]

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                direction=Message.Direction.INBOUND,
                message_type=Message.MessageType.TEXT,
                content="Duplicate",
                whatsapp_message_id="wamid.1",
            )
