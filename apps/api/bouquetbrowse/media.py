import hashlib
import io
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import get_settings
from .providers import CapabilityError

Image.MAX_IMAGE_PIXELS = 20_000_000


def validate_remote_url(url):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    own_storage = urlparse(get_settings().supabase_url).hostname
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise CapabilityError("Media must use an HTTPS source URL without credentials.", "unsafe_media_url")
    if not (host.endswith(".fbcdn.net") or host.endswith(".cdninstagram.com") or own_storage and host == own_storage):
        raise CapabilityError(
            "Use an official source CDN or this pilot's configured storage host.", "unsupported_media_host"
        )
    addresses = {record[4][0] for record in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise CapabilityError("Media destination is not a public address.", "unsafe_media_url")
    return host, sorted(addresses)[0]


def download_media(url):
    host, address = validate_remote_url(url)
    # Pin the resolved address, retaining Host and TLS SNI, to prevent DNS-rebinding between validation and fetch.
    request = httpx.Request(
        "GET", httpx.URL(url).copy_with(host=address), headers={"Host": host}, extensions={"sni_hostname": host}
    )
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        response = client.send(request, stream=True)
        try:
            if response.status_code != 200:
                raise CapabilityError("Media could not be retrieved; redirects are not followed.", "media_unavailable")
            chunks, length = [], 0
            for chunk in response.iter_bytes():
                length += len(chunk)
                if length > 10 * 1024 * 1024:
                    raise CapabilityError("Media exceeds the 10 MB limit.", "media_too_large")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            response.close()


def prepare_media(raw: bytes):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Image exceeds 10 MB")
    try:
        with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Only JPEG, PNG and WebP are supported")
            source.verify()
        with Image.open(io.BytesIO(raw), formats=["JPEG", "PNG", "WEBP"]) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            if image.width * image.height > 20_000_000:
                raise ValueError("Image pixel limit exceeded")
            image.thumbnail((1200, 1200))
            result = io.BytesIO()
            image.save(result, format="JPEG", quality=84, optimize=True)
            return result.getvalue(), {
                "checksum": hashlib.sha256(raw).hexdigest(),
                "perceptual_hash": str(imagehash.phash(image)),
                "width": image.width,
                "height": image.height,
                "mime": "image/jpeg",
            }
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError("Invalid or oversized image") from exc


def save_media(raw: bytes):
    encoded, metadata = prepare_media(raw)
    key = metadata["checksum"] + ".jpg"
    from .storage import put_media

    put_media(key, encoded)
    return key, encoded, metadata


def local_media_path(key):
    root = get_settings().media_dir.resolve()
    path = (root / key).resolve()
    if path.parent != root or not path.is_file():
        raise FileNotFoundError("Media not found")
    return path
