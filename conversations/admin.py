# Register your models here.
from django.contrib import admin

from conversations.models import Conversation, EndUser, Message


@admin.register(EndUser)
class EndUserAdmin(admin.ModelAdmin):
    list_display = (
        "phone_number",
        "display_name",
        "tenant",
        "preferred_language",
        "created_at",
    )
    list_filter = (
        "tenant",
        "preferred_language",
    )
    search_fields = (
        "phone_number",
        "display_name",
        "tenant__business_name",
    )


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "end_user",
        "status",
        "assigned_staff",
        "started_at",
        "last_message_at",
    )
    list_filter = (
        "status",
        "tenant",
    )
    search_fields = (
        "end_user__phone_number",
        "tenant__business_name",
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "direction",
        "message_type",
        "whatsapp_message_id",
        "created_at",
    )
    list_filter = (
        "direction",
        "message_type",
    )
    search_fields = (
        "whatsapp_message_id",
        "content",
        "conversation__end_user__phone_number",
    )
