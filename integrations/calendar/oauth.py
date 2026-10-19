"""OAuth authorization configuration for external calendars."""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings

from tenants.models import Tenant


@dataclass(frozen=True)
class OAuthConfig:
    authorization_url: str
    token_url: str
    client_id: str
    scopes: tuple[str, ...]


def get_oauth_config(provider: str) -> OAuthConfig:
    """Return the configured OAuth endpoints and scopes."""
    if provider == Tenant.CalendarProvider.GOOGLE:
        return OAuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
            scopes=(
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.freebusy",
                "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            ),
        )

    if provider == Tenant.CalendarProvider.OUTLOOK:
        tenant = settings.MICROSOFT_CALENDAR_TENANT

        return OAuthConfig(
            authorization_url=(
                f"https://login.microsoftonline.com/" f"{tenant}/oauth2/v2.0/authorize"
            ),
            token_url=(
                f"https://login.microsoftonline.com/" f"{tenant}/oauth2/v2.0/token"
            ),
            client_id=settings.MICROSOFT_CALENDAR_CLIENT_ID,
            scopes=(
                "offline_access",
                "Calendars.ReadWrite",
            ),
        )

    raise ValueError("Unsupported calendar OAuth provider.")


def build_authorization_url(
    *,
    provider: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    """Build a provider authorization URL using PKCE."""
    config = get_oauth_config(provider)

    if not config.client_id:
        raise ValueError("Calendar OAuth client ID is not configured.")

    params = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    if provider == Tenant.CalendarProvider.GOOGLE:
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    return f"{config.authorization_url}?{urlencode(params)}"


def exchange_authorization_code(
    *,
    provider: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict:
    """Exchange an authorization code for OAuth tokens."""
    from integrations.calendar.http import request_json

    config = get_oauth_config(provider)

    if provider == Tenant.CalendarProvider.GOOGLE:
        client_secret = settings.GOOGLE_CALENDAR_CLIENT_SECRET
    elif provider == Tenant.CalendarProvider.OUTLOOK:
        client_secret = settings.MICROSOFT_CALENDAR_CLIENT_SECRET
    else:
        raise ValueError("Unsupported calendar OAuth provider.")

    if not config.client_id or not client_secret:
        raise ValueError("Calendar OAuth credentials are not configured.")

    return request_json(
        config.token_url,
        method="POST",
        form={
            "client_id": config.client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
        },
    )


def discover_calendar_id(*, provider: str, access_token: str) -> str:
    """Find a usable calendar ID for the authenticated account."""
    from integrations.calendar.base import CalendarProviderError
    from integrations.calendar.http import request_json

    if provider == Tenant.CalendarProvider.GOOGLE:
        payload = request_json(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList/primary",
            access_token=access_token,
        )
    elif provider == Tenant.CalendarProvider.OUTLOOK:
        payload = request_json(
            "https://graph.microsoft.com/v1.0/me/calendar",
            access_token=access_token,
        )
    else:
        raise ValueError("Unsupported calendar OAuth provider.")

    calendar_id = payload.get("id")

    if not isinstance(calendar_id, str) or not calendar_id.strip():
        raise CalendarProviderError(
            "Calendar provider did not return a usable calendar ID."
        )

    return calendar_id
