import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v26.0"
GRAPH_API_BASE_URL = "https://graph.facebook.com"


def send_text_message(
    tenant,
    to_phone_number,
    text,
):
    """Send one WhatsApp text message for the given tenant."""

    if not tenant.phone_number_id or not tenant.whatsapp_access_token:
        logger.error(
            "Cannot send WhatsApp message: missing tenant credentials " "tenant_id=%s",
            tenant.pk,
        )
        return False

    access_token = tenant.whatsapp_access_token

    if isinstance(access_token, memoryview):
        access_token = bytes(access_token)

    if isinstance(access_token, bytes):
        access_token = access_token.decode("utf-8")

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

    return True
