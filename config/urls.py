"""
URL configuration for config project.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import dashboard_home, staff_integrations
from bookings.views import BookingListView
from core.views import healthcheck
from integrations.calendar.oauth_views import (
    calendar_oauth_callback,
    calendar_oauth_connect,
)
from integrations.views import whatsapp_webhook

urlpatterns = [
    path(
        "integrations/calendar/<str:provider>/connect/",
        calendar_oauth_connect,
        name="calendar-oauth-connect",
    ),
    path(
        "integrations/calendar/<str:provider>/callback/",
        calendar_oauth_callback,
        name="calendar-oauth-callback",
    ),
    path(
        "integrations/",
        staff_integrations,
        name="staff-integrations",
    ),
    path(
        "",
        RedirectView.as_view(pattern_name="dashboard", permanent=False),
        name="home",
    ),
    path("admin/", admin.site.urls),
    path("conversations/", include("conversations.urls")),
    path("health/", healthcheck, name="healthcheck"),
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp-webhook"),
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
