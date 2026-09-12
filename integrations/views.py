import hashlib
import hmac
from secrets import compare_digest

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt


def _has_valid_whatsapp_signature(request):
    signature = request.headers.get("X-Hub-Signature-256", "")
    app_secret = settings.META_APP_SECRET

    if not signature or not app_secret:
        return False

    expected_signature = (
        "sha256="
        + hmac.new(
            app_secret.encode("utf-8"),
            request.body,
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(
        signature,
        expected_signature,
    )


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode", "")
        verify_token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")

        if mode == "subscribe" and compare_digest(
            verify_token,
            settings.WHATSAPP_VERIFY_TOKEN,
        ):
            return HttpResponse(
                challenge,
                content_type="text/plain",
            )

        return HttpResponseForbidden()

    if request.method == "POST":
        if not _has_valid_whatsapp_signature(request):
            return HttpResponseForbidden()

        return HttpResponse(status=200)

    return HttpResponseNotAllowed(["GET", "POST"])
