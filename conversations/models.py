from django.db import models

from tenants.models import Tenant


class EndUser(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )
    phone_number = models.CharField(max_length=16)
    display_name = models.CharField(max_length=255, blank=True)
    preferred_language = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "phone_number"],
                name="unique_enduser_tenant_phone",
            )
        ]

    def __str__(self):
        return self.display_name or self.phone_number


class Conversation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        AWAITING_USER = "awaiting_user", "Awaiting User"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )
    end_user = models.ForeignKey(
        EndUser,
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    pending_intent_state = models.JSONField(default=dict)
    assigned_staff = models.ForeignKey(
        "accounts.StaffUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation {self.pk} ({self.status})"


class Message(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class MessageType(models.TextChoices):
        TEXT = "text", "Text"
        AUDIO = "audio", "Audio"
        IMAGE = "image", "Image"
        SYSTEM = "system", "System"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
    )
    direction = models.CharField(
        max_length=8,
        choices=Direction.choices,
    )
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
    )
    content = models.TextField(blank=True)
    media_reference = models.CharField(max_length=255, blank=True)
    whatsapp_message_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    raw_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["conversation", "created_at"],
                name="message_conv_created_idx",
            ),
        ]

    def __str__(self):
        stamp = f"{self.created_at:%Y-%m-%d %H:%M}"
        return f"{self.direction} {self.message_type} at {stamp}"
