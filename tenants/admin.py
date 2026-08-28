# Register your models here.
from django.contrib import admin

from tenants.models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "vertical",
        "calendar_provider",
        "subscription_tier",
        "is_active",
        "created_at",
    )
    list_filter = (
        "vertical",
        "calendar_provider",
        "subscription_tier",
        "is_active",
    )
    search_fields = (
        "business_name",
        "waba_id",
        "phone_number_id",
    )
