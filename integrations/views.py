import hashlib
import hmac
import json
import logging
from secrets import compare_digest

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)
from django.views.decorators.csrf import csrf_exempt

from conversations.models import Conversation, EndUser, Message
from integrations.tasks import buffer_inbound_message
from tenants.models import Tenant

logger = logging.getLogger(__name__)


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


def _extract_whatsapp_message(payload):
    value = payload["entry"][0]["changes"][0]["value"]
    message = value["messages"][0]

    message_type = message["type"]

    if message_type == "text":
        content = message.get("text", {}).get("body", "")
    else:
        # Audio/image transcription or description is handled later.
        content = ""

    return {
        "phone_number_id": value["metadata"]["phone_number_id"],
        "sender_phone_number": message["from"],
        "message_content": content,
        "message_type": message_type,
        "whatsapp_message_id": message["id"],
    }


def _resolve_whatsapp_context(payload):
    message_data = _extract_whatsapp_message(payload)

    try:
        tenant = Tenant.objects.get(
            phone_number_id=message_data["phone_number_id"],
        )
    except Tenant.DoesNotExist:
        logger.warning(
            "Ignoring WhatsApp webhook for unknown phone_number_id=%s",
            message_data["phone_number_id"],
        )
        return None

    end_user, _ = EndUser.objects.get_or_create(
        tenant=tenant,
        phone_number=message_data["sender_phone_number"],
    )

    conversation = (
        Conversation.objects.filter(
            tenant=tenant,
            end_user=end_user,
            status=Conversation.Status.ACTIVE,
        )
        .order_by("started_at")
        .first()
    )

    if conversation is None:
        conversation = Conversation.objects.create(
            tenant=tenant,
            end_user=end_user,
            status=Conversation.Status.ACTIVE,
        )

    return {
        "tenant": tenant,
        "end_user": end_user,
        "conversation": conversation,
        "message_content": message_data["message_content"],
    }


def _persist_inbound_message(payload, resolved_context):
    message_data = _extract_whatsapp_message(payload)

    return Message.objects.get_or_create(
        whatsapp_message_id=message_data["whatsapp_message_id"],
        defaults={
            "conversation": resolved_context["conversation"],
            "direction": Message.Direction.INBOUND,
            "message_type": message_data["message_type"],
            "content": message_data["message_content"],
            "raw_payload": payload,
        },
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
        # Ticket 5: signature verification happens before parsing.
        if not _has_valid_whatsapp_signature(request):
            return HttpResponseForbidden()

        try:
            payload = json.loads(request.body)
            resolved_context = _resolve_whatsapp_context(payload)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ):
            return HttpResponseBadRequest()

        if resolved_context is None:
            return HttpResponse(status=404)

        message, created = _persist_inbound_message(
            payload,
            resolved_context,
        )

        if created:
            buffer_inbound_message(
                resolved_context["tenant"].pk,
                resolved_context["end_user"].pk,
                message.content,
            )

        return HttpResponse(status=200)

    return HttpResponseNotAllowed(["GET", "POST"])
