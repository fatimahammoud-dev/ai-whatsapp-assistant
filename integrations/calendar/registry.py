"""Calendar provider registry."""

from integrations.calendar.google import GoogleCalendarProvider
from integrations.calendar.outlook import OutlookCalendarProvider
from tenants.models import Tenant

_PROVIDERS = {
    Tenant.CalendarProvider.GOOGLE: GoogleCalendarProvider(),
    Tenant.CalendarProvider.OUTLOOK: OutlookCalendarProvider(),
}


def get_calendar_provider(connection):
    """Return the provider implementation for a calendar connection."""
    return _PROVIDERS.get(connection.provider)
