import io

import pytest
from PIL import Image

from bouquetbrowse.media import prepare_media, validate_remote_url
from bouquetbrowse.providers import CapabilityError


def test_image_validation_and_preparation():
    data = io.BytesIO()
    Image.new("RGB", (1600, 1200), "pink").save(data, "PNG")
    encoded, metadata = prepare_media(data.getvalue())
    assert encoded.startswith(b"\xff\xd8")
    assert metadata["width"] == 1200
    assert metadata["height"] == 900
    assert len(metadata["checksum"]) == 64
    assert len(metadata["perceptual_hash"]) == 16


@pytest.mark.parametrize(
    "url",
    [
        "http://scontent.example.fbcdn.net/image.jpg",
        "https://127.0.0.1/image",
        "https://example.com/image.jpg",
        "https://user:password@scontent.example.fbcdn.net/image.jpg",
    ],
)
def test_untrusted_media_urls_rejected(url):
    with pytest.raises(CapabilityError):
        validate_remote_url(url)


def test_private_dns_rejected(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(CapabilityError):
        validate_remote_url("https://scontent.example.fbcdn.net/image.jpg")


def test_non_images_rejected():
    with pytest.raises(ValueError):
        prepare_media(b"<svg onload='bad()'/>")
