import json
import logging
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from integrations.whatsapp import (
    GRAPH_API_VERSION,
    send_text_message,
)
from tenants.models import Tenant

PHONE_NUMBER_ID = "123456789012345"
ACCESS_TOKEN = b"tenant-specific-access-token"
RECIPIENT = "96170123456"


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def tenant(db):
    tenant = Tenant.objects.create(
        business_name="WhatsApp Client Test Business",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id=PHONE_NUMBER_ID,
        whatsapp_access_token=ACCESS_TOKEN,
    )

    tenant.refresh_from_db()

    return tenant


@pytest.mark.django_db
def test_send_text_message_uses_expected_cloud_api_request(
    tenant,
):
    with patch(
        "integrations.whatsapp.urlopen",
        return_value=FakeResponse(200),
    ) as urlopen_mock:
        result = send_text_message(
            tenant,
            RECIPIENT,
            "Hello from the assistant",
        )

    assert result is True
    urlopen_mock.assert_called_once()

    request = urlopen_mock.call_args.args[0]

    assert request.full_url == (
        f"https://graph.facebook.com/"
        f"{GRAPH_API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    assert request.get_method() == "POST"

    headers = {key.lower(): value for key, value in request.header_items()}

    assert headers["authorization"] == ("Bearer tenant-specific-access-token")
    assert headers["content-type"] == "application/json"

    assert json.loads(request.data.decode("utf-8")) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": RECIPIENT,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": "Hello from the assistant",
        },
    }


@pytest.mark.django_db
def test_send_text_message_handles_non_2xx_without_raising(
    tenant,
    caplog,
):
    api_error = HTTPError(
        url=(
            f"https://graph.facebook.com/"
            f"{GRAPH_API_VERSION}/"
            f"{PHONE_NUMBER_ID}/messages"
        ),
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=None,
    )

    with patch(
        "integrations.whatsapp.urlopen",
        side_effect=api_error,
    ):
        with caplog.at_level(
            logging.ERROR,
            logger="integrations.whatsapp",
        ):
            result = send_text_message(
                tenant,
                RECIPIENT,
                "This request will fail",
            )

    assert result is False
    assert "status=400" in caplog.text
