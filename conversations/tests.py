# Create your tests here.
import pytest
from django.db import IntegrityError, transaction

from conversations.models import EndUser
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
