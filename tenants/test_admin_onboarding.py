import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from bookings.models import Service
from tenants.models import Tenant


@pytest.mark.django_db
def test_platform_admin_can_onboard_tenant_through_django_admin(client):
    user_model = get_user_model()
    platform_admin = user_model.objects.create_superuser(
        username="platform_admin",
        password="test-password-123",
        email="admin@example.com",
        role=user_model.Role.PLATFORM_ADMIN,
    )
    client.force_login(platform_admin)

    tenant_response = client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "business_name": "Pilot Clinic",
            "vertical": Tenant.Vertical.DOCTOR,
            "timezone": "Asia/Beirut",
            "waba_id": "",
            "phone_number_id": "",
            "calendar_provider": Tenant.CalendarProvider.INTERNAL,
            "working_hours": '{"monday": [["09:00", "17:00"]]}',
            "default_slot_duration_minutes": "30",
            "booking_buffer_minutes": "0",
            "subscription_tier": Tenant.SubscriptionTier.TRIAL,
            "monthly_conversation_quota": "100",
            "memory_enabled": "on",
            "memory_max_messages": "20",
            "memory_summary_max_chars": "1500",
            "system_prompt_overrides": '{"business_name": "Pilot Clinic"}',
            "language_defaults": '["en"]',
            "is_active": "on",
            "_save": "Save",
        },
    )

    assert tenant_response.status_code == 302

    tenant = Tenant.objects.get(business_name="Pilot Clinic")

    service_response = client.post(
        reverse("admin:bookings_service_add"),
        {
            "tenant": tenant.pk,
            "name": "Consultation",
            "duration_minutes": "30",
            "price": "",
            "is_active": "on",
            "_save": "Save",
        },
    )

    assert service_response.status_code == 302

    service = Service.objects.get(
        tenant=tenant,
        name="Consultation",
    )
    assert service.duration_minutes == 30
    assert service.is_active is True

    staff_response = client.post(
        reverse("admin:accounts_staffuser_add"),
        {
            "username": "pilot_owner",
            "password1": "Strong-test-password-123",
            "password2": "Strong-test-password-123",
            "role": user_model.Role.OWNER,
            "tenant": tenant.pk,
            "_save": "Save",
        },
    )

    assert staff_response.status_code == 302

    staff = user_model.objects.get(username="pilot_owner")
    assert staff.tenant == tenant
    assert staff.role == user_model.Role.OWNER
    assert staff.check_password("Strong-test-password-123")
