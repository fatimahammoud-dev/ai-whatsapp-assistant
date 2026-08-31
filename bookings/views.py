# Create your views here.
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from accounts.mixins import TenantScopedMixin
from bookings.models import Booking


class BookingListView(LoginRequiredMixin, TenantScopedMixin, ListView):
    model = Booking
    template_name = "bookings/booking_list.html"
    context_object_name = "bookings"
