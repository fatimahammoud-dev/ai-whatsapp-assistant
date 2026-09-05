# Create your models here.
from django.core.exceptions import ValidationError
from django.db import models

from tenants.models import Tenant


class Service(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    duration_minutes = models.PositiveIntegerField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No Show"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )
    end_user = models.ForeignKey(
        "conversations.EndUser",
        on_delete=models.CASCADE,
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    external_event_id = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "scheduled_start"],
                condition=models.Q(status="confirmed"),
                name="unique_confirmed_booking_start_per_tenant",
            ),
            models.CheckConstraint(
                condition=models.Q(scheduled_end__gt=models.F("scheduled_start")),
                name="booking_end_after_start",
            ),
        ]

    def __str__(self):
        return f"Booking {self.pk} at {self.scheduled_start:%Y-%m-%d %H:%M}"

    def clean(self):
        super().clean()

        if (
            self.scheduled_start
            and self.scheduled_end
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValidationError(
                {"scheduled_end": "Scheduled end must be after scheduled start."}
            )


class BlockedDate(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "date"],
                name="unique_blocked_date_per_tenant",
            )
        ]

    def __str__(self):
        return f"Blocked {self.date}"
