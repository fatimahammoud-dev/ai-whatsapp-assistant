"""Staff-facing calendar OAuth authorization endpoints."""

import base64
import hashlib
import secrets

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import StaffUser
from integrations.calendar.oauth import build_authorization_url
from tenants.models import Tenant

OAUTH_SESSION_KEY = "calendar_oauth_pending"


def _require_owner(request):
    """Only a tenant owner can change calendar integrations."""
    if request.user.role != StaffUser.Role.OWNER or not request.user.tenant_id:
        raise PermissionDenied("Only a tenant owner can connect calendars.")


def _pkce_challenge(verifier):
    """Return the SHA-256 PKCE challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@login_required
@require_POST
def calendar_oauth_connect(request, provider):
    """Start a calendar OAuth authorization-code flow."""
    _require_owner(request)

    if provider not in (
        Tenant.CalendarProvider.GOOGLE,
        Tenant.CalendarProvider.OUTLOOK,
    ):
        return HttpResponseBadRequest("Unsupported calendar provider.")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    redirect_uri = request.build_absolute_uri(
        reverse("calendar-oauth-callback", kwargs={"provider": provider})
    )

    try:
        authorization_url = build_authorization_url(
            provider=provider,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=_pkce_challenge(code_verifier),
        )
    except ValueError:
        return HttpResponseBadRequest("Calendar OAuth is not configured.")

    request.session[OAUTH_SESSION_KEY] = {
        "state": state,
        "code_verifier": code_verifier,
        "provider": provider,
        "tenant_id": request.user.tenant_id,
        "user_id": request.user.pk,
        "redirect_uri": redirect_uri,
    }

    return redirect(authorization_url)


@login_required
def calendar_oauth_callback(request, provider):
    """Validate OAuth callback and persist the connected calendar."""
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from integrations.calendar.base import CalendarProviderError
    from integrations.calendar.oauth import (
        discover_calendar_id,
        exchange_authorization_code,
    )
    from integrations.models import CalendarConnection

    _require_owner(request)

    pending = request.session.pop(OAUTH_SESSION_KEY, None)

    if not isinstance(pending, dict):
        return HttpResponseBadRequest("OAuth session is missing or expired.")

    received_state = request.GET.get("state", "")

    if (
        provider
        not in (
            Tenant.CalendarProvider.GOOGLE,
            Tenant.CalendarProvider.OUTLOOK,
        )
        or not received_state
        or not secrets.compare_digest(str(pending.get("state", "")), received_state)
        or pending.get("provider") != provider
        or pending.get("tenant_id") != request.user.tenant_id
        or pending.get("user_id") != request.user.pk
    ):
        return HttpResponseBadRequest("Invalid OAuth callback.")

    if request.GET.get("error"):
        return HttpResponseBadRequest("Calendar authorization was denied.")

    code = request.GET.get("code")

    if not code:
        return HttpResponseBadRequest("Authorization code is missing.")

    try:
        tokens = exchange_authorization_code(
            provider=provider,
            code=code,
            redirect_uri=pending["redirect_uri"],
            code_verifier=pending["code_verifier"],
        )

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")

        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
            or not isinstance(expires_in, (int, float))
            or expires_in <= 0
        ):
            raise CalendarProviderError(
                "OAuth token response is missing required credentials."
            )

        calendar_id = discover_calendar_id(
            provider=provider,
            access_token=access_token,
        )

        with transaction.atomic():
            CalendarConnection.objects.update_or_create(
                tenant_id=request.user.tenant_id,
                defaults={
                    "provider": provider,
                    "external_calendar_id": calendar_id,
                    "access_token": access_token.encode("utf-8"),
                    "refresh_token": refresh_token.encode("utf-8"),
                    "token_expires_at": timezone.now() + timedelta(seconds=expires_in),
                    "scopes": (
                        tokens.get("scope", "").split()
                        if isinstance(tokens.get("scope", ""), str)
                        else []
                    ),
                },
            )

            Tenant.objects.filter(
                pk=request.user.tenant_id,
            ).update(calendar_provider=provider)

    except (CalendarProviderError, ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Calendar connection failed.")

    return redirect("staff-integrations")
