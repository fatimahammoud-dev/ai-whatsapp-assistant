from django.contrib.auth.models import AbstractUser
from django.db import models

from tenants.models import Tenant


class StaffUser(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        STAFF = "staff", "Staff"
        PLATFORM_ADMIN = "platform_admin", "Platform Admin"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STAFF,
    )
