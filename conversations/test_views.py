import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from conversations.models import Conversation, EndUser, Message
from tenants.models import Tenant


def create_staff_user(*, username, tenant):
    user_model = get_user_model()
    return user_model.objects.create_user(
        username=username,
        password="test-password",
        tenant=tenant,
    )


def create_conversation(
    *,
    tenant,
    phone_number,
    display_name="",
    status=Conversation.Status.ACTIVE,
):
    end_user = EndUser.objects.create(
        tenant=tenant,
        phone_number=phone_number,
        display_name=display_name,
    )
    return Conversation.objects.create(
        tenant=tenant,
        end_user=end_user,
        status=status,
    )


@pytest.mark.django_db
def test_conversation_list_requires_login(client):
    response = client.get("/conversations/")

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_conversation_list_shows_only_logged_in_users_tenant(client):
    tenant_a = Tenant.objects.create(
        business_name="Clinic A",
        vertical="doctor",
    )
    tenant_b = Tenant.objects.create(
        business_name="Clinic B",
        vertical="doctor",
    )

    user = create_staff_user(
        username="staff-a",
        tenant=tenant_a,
    )

    own_conversation = create_conversation(
        tenant=tenant_a,
        phone_number="+96170111111",
        display_name="Own Client",
    )
    other_conversation = create_conversation(
        tenant=tenant_b,
        phone_number="+96170222222",
        display_name="Other Client",
    )

    client.force_login(user)
    response = client.get(reverse("conversation-list"))

    assert response.status_code == 200
    conversations = list(response.context["conversations"])

    assert own_conversation in conversations
    assert other_conversation not in conversations

    content = response.content.decode()
    assert "Own Client" in content
    assert "Other Client" not in content


@pytest.mark.django_db
def test_conversation_list_shows_status_and_last_message_at(client):
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    user = create_staff_user(
        username="staff",
        tenant=tenant,
    )
    conversation = create_conversation(
        tenant=tenant,
        phone_number="+96170333333",
        display_name="List Client",
        status=Conversation.Status.AWAITING_USER,
    )

    client.force_login(user)
    response = client.get(reverse("conversation-list"))

    assert response.status_code == 200
    content = response.content.decode()

    assert "List Client" in content
    assert conversation.get_status_display() in content
    last_message_date = timezone.localtime(conversation.last_message_at).strftime(
        "%Y-%m-%d"
    )
    assert last_message_date in content


@pytest.mark.django_db
def test_conversation_detail_shows_messages_in_chronological_order(client):
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    user = create_staff_user(
        username="staff",
        tenant=tenant,
    )
    conversation = create_conversation(
        tenant=tenant,
        phone_number="+96170444444",
        display_name="Detail Client",
    )

    first_message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="First message",
    )
    second_message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
        message_type=Message.MessageType.TEXT,
        content="Second message",
    )

    client.force_login(user)
    response = client.get(
        reverse(
            "conversation-detail",
            kwargs={"pk": conversation.pk},
        )
    )

    assert response.status_code == 200

    messages = list(response.context["messages"])
    assert messages == [first_message, second_message]

    content = response.content.decode()
    assert content.index("First message") < content.index("Second message")
    assert first_message.get_direction_display() in content
    assert second_message.get_direction_display() in content


@pytest.mark.django_db
def test_conversation_detail_cannot_access_another_tenants_conversation(client):
    tenant_a = Tenant.objects.create(
        business_name="Clinic A",
        vertical="doctor",
    )
    tenant_b = Tenant.objects.create(
        business_name="Clinic B",
        vertical="doctor",
    )

    user = create_staff_user(
        username="staff-a",
        tenant=tenant_a,
    )

    other_conversation = create_conversation(
        tenant=tenant_b,
        phone_number="+96170555555",
        display_name="Private Client",
    )

    Message.objects.create(
        conversation=other_conversation,
        direction=Message.Direction.INBOUND,
        message_type=Message.MessageType.TEXT,
        content="Private tenant message",
    )

    client.force_login(user)
    response = client.get(
        reverse(
            "conversation-detail",
            kwargs={"pk": other_conversation.pk},
        )
    )

    assert response.status_code == 404
    assert "Private tenant message" not in response.content.decode()


@pytest.mark.django_db
def test_conversation_detail_requires_login(client):
    tenant = Tenant.objects.create(
        business_name="Test Clinic",
        vertical="doctor",
    )
    conversation = create_conversation(
        tenant=tenant,
        phone_number="+96170666666",
    )

    response = client.get(f"/conversations/{conversation.pk}/")

    assert response.status_code == 302
    assert "/login/" in response.url
