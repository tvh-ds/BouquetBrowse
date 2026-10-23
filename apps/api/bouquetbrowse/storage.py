"""Private managed storage in pilot mode; local files in localhost demo mode."""

import re

import httpx

from .config import get_settings
from .providers import CapabilityError


def validate_key(key):
    if not re.fullmatch(r"[a-f0-9]{64}\.jpg", key):
        raise ValueError("Invalid managed media key")
    return key


def storage_headers():
    key = get_settings().supabase_secret_key
    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def put_media(key, content):
    s = get_settings()
    validate_key(key)
    if s.app_mode == "pilot":
        response = httpx.post(
            f"{s.supabase_url}/storage/v1/object/{s.supabase_storage_bucket}/{key}",
            headers={**storage_headers(), "Content-Type": "image/jpeg", "x-upsert": "true"},
            content=content,
            timeout=30,
            follow_redirects=False,
        )
        if response.status_code not in {200, 201}:
            raise CapabilityError(
                "Private storage upload failed. Check bucket and server credentials.",
                "storage_upload_failed",
                retryable=response.status_code >= 500,
            )
    else:
        root = s.media_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(content)


def get_media_bytes(key):
    s = get_settings()
    validate_key(key)
    if s.app_mode == "pilot":
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            with client.stream(
                "GET",
                f"{s.supabase_url}/storage/v1/object/authenticated/{s.supabase_storage_bucket}/{key}",
                headers=storage_headers(),
            ) as response:
                if response.status_code != 200:
                    raise FileNotFoundError("Private media is unavailable")
                content, length = [], 0
                for chunk in response.iter_bytes():
                    length += len(chunk)
                    if length > 10 * 1024 * 1024:
                        raise ValueError("Stored media exceeds size limit")
                    content.append(chunk)
                return b"".join(content)
    from .media import local_media_path

    return local_media_path(key).read_bytes()


def delete_media(key):
    s = get_settings()
    validate_key(key)
    if s.app_mode == "pilot":
        response = httpx.request(
            "DELETE",
            f"{s.supabase_url}/storage/v1/object/{s.supabase_storage_bucket}",
            headers=storage_headers(),
            json={"prefixes": [key]},
            timeout=20,
            follow_redirects=False,
        )
        if response.status_code not in {200, 404}:
            raise CapabilityError(
                "Storage deletion failed; the purge must be retried.", "storage_delete_failed", retryable=True
            )
    else:
        from .media import local_media_path

        try:
            local_media_path(key).unlink()
        except FileNotFoundError:
            pass
