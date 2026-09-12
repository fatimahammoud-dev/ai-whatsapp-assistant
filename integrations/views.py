from secrets import compare_digest

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden


def whatsapp_webhook(request):
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
