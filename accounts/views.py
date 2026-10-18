from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from bookings.models import Booking
from integrations.models import CalendarConnection
from tenants.models import Tenant


@login_required
def dashboard_home(request):
    upcoming_bookings = Booking.objects.none()

    if request.user.tenant_id:
        upcoming_bookings = (
            Booking.objects.filter(
                tenant_id=request.user.tenant_id,
                status=Booking.Status.CONFIRMED,
                scheduled_start__gte=timezone.now(),
            )
            .select_related("end_user", "service")
            .order_by("scheduled_start", "pk")
        )

    return render(
        request,
        "dashboard.html",
        {"upcoming_bookings": upcoming_bookings},
    )


@login_required
def staff_integrations(request):
    connection = None

    if request.user.tenant_id:
        connection = CalendarConnection.objects.filter(
            tenant_id=request.user.tenant_id,
        ).first()

    connected_provider = connection.provider if connection else None

    return render(
        request,
        "staff/integrations.html",
        {
            "connected_provider": connected_provider,
            "google_provider": Tenant.CalendarProvider.GOOGLE,
            "outlook_provider": Tenant.CalendarProvider.OUTLOOK,
            "can_manage_calendar": (
                request.user.role == "owner" and request.user.tenant_id is not None
            ),
        },
    )
