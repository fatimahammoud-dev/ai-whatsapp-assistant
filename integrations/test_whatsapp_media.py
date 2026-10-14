import json
from unittest.mock import Mock

import pytest

from integrations.whatsapp import (
    GRAPH_API_BASE_URL,
    GRAPH_API_VERSION,
    download_media,
)
from tenants.models import Tenant


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.body


@pytest.mark.django_db
def test_download_media_fetches_metadata_then_audio(
    monkeypatch,
):
    tenant = Tenant.objects.create(
        business_name="Media Test",
        vertical=Tenant.Vertical.DOCTOR,
        phone_number_id="phone-id",
        whatsapp_access_token=b"secret-token",
    )

    metadata_url = f"{GRAPH_API_BASE_URL}/" f"{GRAPH_API_VERSION}/" "media-123"

    media_url = "https://media.example.test/audio.ogg"

    responses = [
        FakeResponse(
            json.dumps(
                {
                    "url": media_url,
                    "mime_type": "audio/ogg",
                }
            ).encode("utf-8")
        ),
        FakeResponse(b"audio-bytes"),
    ]

    urlopen_mock = Mock(side_effect=responses)

    monkeypatch.setattr(
        "integrations.whatsapp.urlopen",
        urlopen_mock,
    )

    media_bytes, mime_type = download_media(
        tenant,
        "media-123",
    )

    assert media_bytes == b"audio-bytes"
    assert mime_type == "audio/ogg"
    assert urlopen_mock.call_count == 2

    metadata_request = urlopen_mock.call_args_list[0].args[0]
    media_request = urlopen_mock.call_args_list[1].args[0]

    assert metadata_request.full_url == metadata_url
    assert media_request.full_url == media_url

    assert metadata_request.get_header("Authorization") == "Bearer secret-token"
    assert media_request.get_header("Authorization") == "Bearer secret-token"
