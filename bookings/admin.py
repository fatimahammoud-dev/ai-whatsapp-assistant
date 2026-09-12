from django.contrib import admin

from bookings.models import BlockedDate, Booking, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tenant",
        "duration_minutes",
        "is_active",
    )
    list_filter = (
        "is_active",
        "tenant",
    )
    search_fields = (
        "name",
        "tenant__business_name",
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "end_user",
        "service",
        "scheduled_start",
        "scheduled_end",
        "status",
    )
    list_filter = (
        "status",
        "tenant",
        "service",
    )
    search_fields = (
        "end_user__phone_number",
        "external_event_id",
        "service__name",
    )


@admin.register(BlockedDate)
class BlockedDateAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "date",
        "reason",
    )
    list_filter = ("tenant",)
    search_fields = (
        "reason",
        "tenant__business_name",
    )
