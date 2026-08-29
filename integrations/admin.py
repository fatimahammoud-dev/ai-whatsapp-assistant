# Register your models here.
from django.contrib import admin

from integrations.models import CalendarConnection


@admin.register(CalendarConnection)
class CalendarConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "provider",
        "external_calendar_id",
        "connected_at",
        "last_synced_at",
    )
    list_filter = ("provider",)
    search_fields = (
        "tenant__business_name",
        "external_calendar_id",
    )
