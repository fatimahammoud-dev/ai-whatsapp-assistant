"""
URL configuration for config project.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from accounts.views import dashboard_home
from bookings.views import BookingListView
from core.views import healthcheck

urlpatterns = [
    path(
        "",
        RedirectView.as_view(pattern_name="dashboard", permanent=False),
        name="home",
    ),
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "dashboard/",
        dashboard_home,
        name="dashboard",
    ),
    path(
        "bookings/",
        BookingListView.as_view(),
        name="booking-list",
    ),
]
