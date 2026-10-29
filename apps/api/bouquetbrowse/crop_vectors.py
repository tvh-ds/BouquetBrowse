"""Feature extraction never substitutes a whole collage for a reviewed product crop."""

from sqlalchemy import select

from .conversation_models import OfferAssociation, OfferOccurrence
from .db import aware, utcnow
from .models import MediaAsset, PostVersion
from .pipeline import digest, enqueue
from .providers import CapabilityError
from .recognition import crop_image
from .recognition_contracts import RegionBounds
from .research_models import CropEmbedding


def checked(db, payload):
    association = db.get(OfferAssociation, payload["association_id"])
    asset = db.get(MediaAsset, association.media_id) if association else None
    offer = db.get(OfferOccurrence, association.offer_id) if association else None
    source = db.get(PostVersion, association.version_id) if association else None
    if (
        not association
        or association.state != "accepted"
        or association.basis != "reviewed_region"
        or not association.region
        or digest(association.region) != payload["region_hash"]
        or not asset
        or asset.state != "ready"
        or not asset.storage_key
        or asset.checksum != payload["checksum"]
        or not asset.retention_until
        or aware(asset.retention_until) <= utcnow()
        or not source
        or aware(source.retention_until) <= utcnow()
        or not offer
        or offer.state in {"withdrawn", "expired", "rejected", "split"}
    ):
        raise CapabilityError("Reviewed crop changed or expired.", "stale_crop")
    return association, asset, source


def enqueue_crop(db, association, revision):
    asset = db.get(MediaAsset, association.media_id)
    payload = {
        "association_id": association.id,
        "checksum": asset.checksum,
        "region_hash": digest(association.region),
        "model_revision": revision,
    }
    return enqueue(db, "embed-crop", payload, f"crop:{digest(payload)}")


def prepare(db_factory, payload, encoder=None):
    from .storage import get_media_bytes
    from .vision import image_embedding

    with db_factory() as db:
        association, asset, _ = checked(db, payload)
        key, region = asset.storage_key, list(association.region)
    content = crop_image(
        get_media_bytes(key), RegionBounds(left=region[0], top=region[1], right=region[2], bottom=region[3])
    )
    return (encoder or image_embedding)(content, payload["model_revision"])


def commit(db, payload, prepared):
    import math

    association, asset, source = checked(db, payload)
    vector, model = prepared
    if len(vector) != 768 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
        raise ValueError("Crop features require 768 finite dimensions")
    from .vision import MODEL

    if model != f"{MODEL}@{payload['model_revision']}":
        raise ValueError("Crop vector model differs from its pinned job")
    if not db.scalar(
        select(CropEmbedding.id).where(
            CropEmbedding.association_id == association.id,
            CropEmbedding.checksum == asset.checksum,
            CropEmbedding.region_hash == payload["region_hash"],
            CropEmbedding.model_version == model,
        )
    ):
        db.add(
            CropEmbedding(
                association_id=association.id,
                media_id=asset.id,
                checksum=asset.checksum,
                region_hash=payload["region_hash"],
                model_version=model,
                vector=vector,
                retention_until=min(aware(asset.retention_until), aware(source.retention_until)),
            )
        )
    return {"embedded": True, "model": model}
