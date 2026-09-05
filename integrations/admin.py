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
    readonly_fields = (
        "tenant",
        "provider",
        "external_calendar_id",
        "token_expires_at",
        "scopes",
        "connected_at",
        "last_synced_at",
    )

    def has_add_permission(self, request):
        """Connections are created by the OAuth callback, not by hand.

        access_token and refresh_token are BinaryFields, which Django excludes
        from ModelForms, so an admin-created row silently got empty tokens and
        looked connected while being unusable.
        """
        return False

    def has_change_permission(self, request, obj=None):
        return False
