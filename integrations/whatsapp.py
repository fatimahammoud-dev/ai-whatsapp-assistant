import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from conversations.models import Conversation, Message

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v26.0"
GRAPH_API_BASE_URL = "https://graph.facebook.com"


class WhatsAppMediaDownloadError(RuntimeError):
    """Raised when WhatsApp media cannot be downloaded."""


def _access_token_text(tenant):
    """Return the tenant WhatsApp access token as text."""
    access_token = tenant.whatsapp_access_token

    if isinstance(access_token, memoryview):
        access_token = bytes(access_token)

    if isinstance(access_token, bytes):
        access_token = access_token.decode("utf-8")

    return access_token


def download_media(tenant, media_reference):
    """Download one WhatsApp media object from Meta's Graph API."""
    if not media_reference:
        raise WhatsAppMediaDownloadError(
            "Cannot download WhatsApp media without a media reference."
        )

    if not tenant.whatsapp_access_token:
        raise WhatsAppMediaDownloadError(
            "Cannot download WhatsApp media without tenant credentials."
        )

    access_token = _access_token_text(tenant)

    metadata_url = f"{GRAPH_API_BASE_URL}/" f"{GRAPH_API_VERSION}/" f"{media_reference}"

    metadata_request = Request(
        metadata_url,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )

    try:
        with urlopen(metadata_request) as response:
            status = response.getcode()

            if not 200 <= status < 300:
                raise WhatsAppMediaDownloadError(
                    "WhatsApp media metadata request returned " f"status={status}."
                )

            metadata = json.loads(response.read().decode("utf-8"))

        media_url = metadata.get("url")

        if not media_url:
            raise WhatsAppMediaDownloadError(
                "WhatsApp media metadata did not contain a download URL."
            )

        media_request = Request(
            media_url,
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            method="GET",
        )

        with urlopen(media_request) as response:
            status = response.getcode()

            if not 200 <= status < 300:
                raise WhatsAppMediaDownloadError(
                    "WhatsApp media download returned " f"status={status}."
                )

            media_bytes = response.read()

    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise WhatsAppMediaDownloadError("WhatsApp media download failed.") from exc

    mime_type = metadata.get(
        "mime_type",
        "application/octet-stream",
    )

    return media_bytes, mime_type


def _active_conversation_for_recipient(
    tenant,
    to_phone_number,
):
    return (
        Conversation.objects.filter(
            tenant=tenant,
            end_user__phone_number=to_phone_number,
            status=Conversation.Status.ACTIVE,
        )
        .order_by("-started_at")
        .first()
    )


def _log_successful_outbound_message(
    tenant,
    to_phone_number,
    text,
):
    conversation = _active_conversation_for_recipient(
        tenant,
        to_phone_number,
    )

    if conversation is None:
        logger.error(
            "WhatsApp message was sent but no active conversation "
            "was found for outbound logging tenant_id=%s",
            tenant.pk,
        )
        return

    Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
        message_type=Message.MessageType.TEXT,
        content=text,
    )


def send_text_message(
    tenant,
    to_phone_number,
    text,
):
    """Send one WhatsApp text message for the given tenant.

    Failure policy:
    A failed API send is logged but is not persisted as an outbound Message.
    """

    if not tenant.phone_number_id or not tenant.whatsapp_access_token:
        logger.error(
            "Cannot send WhatsApp message: missing tenant credentials " "tenant_id=%s",
            tenant.pk,
        )
        return False

    access_token = _access_token_text(tenant)

    url = (
        f"{GRAPH_API_BASE_URL}/"
        f"{GRAPH_API_VERSION}/"
        f"{tenant.phone_number_id}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request) as response:
            status = response.getcode()

            if not 200 <= status < 300:
                logger.error(
                    "WhatsApp Cloud API returned non-2xx response "
                    "status=%s tenant_id=%s",
                    status,
                    tenant.pk,
                )
                return False

    except HTTPError as exc:
        logger.error(
            "WhatsApp Cloud API returned non-2xx response " "status=%s tenant_id=%s",
            exc.code,
            tenant.pk,
        )
        return False

    except URLError as exc:
        logger.error(
            "WhatsApp Cloud API request failed tenant_id=%s reason=%s",
            tenant.pk,
            exc.reason,
        )
        return False

    _log_successful_outbound_message(
        tenant,
        to_phone_number,
        text,
    )

    return True
