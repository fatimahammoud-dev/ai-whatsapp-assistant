"""Every model needs a readable __str__: admin dropdowns and list columns
render related objects through it, and the default shows "Booking object (5)".
"""

from datetime import date, timedelta

import pytest
from django.apps import apps
from django.utils import timezone

from accounts.models import StaffUser
from bookings.models import BlockedDate, Booking, Service
from conversations.models import Conversation, EndUser, Message
from integrations.models import CalendarConnection
from tenants.models import Tenant

PROJECT_APPS = [
    "accounts",
    "bookings",
    "conversations",
    "core",
    "integrations",
    "tenants",
]


def test_every_project_model_defines_str():
    missing = [
        f"{model._meta.app_label}.{model.__name__}"
        for model in apps.get_models()
        if model._meta.app_label in PROJECT_APPS
        and "__str__" not in model.__dict__
        and not issubclass(model, StaffUser)
    ]

    assert missing == []


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(business_name="Str Clinic", vertical="doctor")


@pytest.fixture
def end_user(tenant):
    return EndUser.objects.create(tenant=tenant, phone_number="+96170555555")


def test_service_str(tenant):
    service = Service.objects.create(
        tenant=tenant, name="Consultation", duration_minutes=30
    )

    assert str(service) == "Consultation"


def test_end_user_str_prefers_display_name(tenant):
    end_user = EndUser.objects.create(
        tenant=tenant, phone_number="+96170111111", display_name="Sara"
    )

    assert str(end_user) == "Sara"


def test_end_user_str_falls_back_to_phone_number(end_user):
    assert str(end_user) == "+96170555555"


def test_conversation_str(tenant, end_user):
    conversation = Conversation.objects.create(tenant=tenant, end_user=end_user)

    assert str(conversation) == f"Conversation {conversation.pk} (active)"


def test_message_str(tenant, end_user):
    conversation = Conversation.objects.create(tenant=tenant, end_user=end_user)
    message = Message.objects.create(
        conversation=conversation, direction="inbound", message_type="text"
    )

    assert str(message).startswith("inbound text at ")


def test_booking_str(tenant, end_user):
    start = timezone.now()
    booking = Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )

    assert str(booking) == f"Booking {booking.pk} at {start:%Y-%m-%d %H:%M}"


def test_blocked_date_str(tenant):
    blocked = BlockedDate.objects.create(tenant=tenant, date=date(2026, 1, 2))

    assert str(blocked) == "Blocked 2026-01-02"


def test_calendar_connection_str(tenant):
    connection = CalendarConnection.objects.create(
        tenant=tenant,
        provider="google",
        external_calendar_id="cal-1",
        token_expires_at=timezone.now(),
    )

    assert str(connection) == "Google (cal-1)"


def test_no_model_str_hits_the_database(django_assert_num_queries, tenant, end_user):
    """__str__ must not dereference a related object: the admin renders it once
    per row, so a query there is an N+1."""
    start = timezone.now()
    booking = Booking.objects.create(
        tenant=tenant,
        end_user=end_user,
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=30),
    )
    booking = Booking.objects.get(pk=booking.pk)

    with django_assert_num_queries(0):
        str(booking)
