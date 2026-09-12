# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "role",
        "tenant",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "role",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "tenant__business_name",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Tenant access",
            {
                "fields": (
                    "role",
                    "tenant",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Tenant access",
            {
                "fields": (
                    "role",
                    "tenant",
                )
            },
        ),
    )
