from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from bookings.models import Booking


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
