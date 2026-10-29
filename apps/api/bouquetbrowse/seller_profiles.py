"""Conservative public business facts; neutral/buyer accounts do not become dossiers."""

import re

from sqlalchemy import select

from .conversation_models import CaptureMember, ConversationCapture
from .db import aware, utcnow
from .extraction import extract_caption
from .models import PostVersion, Seller, SourceAccount, SourcePost
from .offers import location_language, seller_language
from .projection import seller_fact
from .publication_gates import publication_ready


def project_business_capture(db, capture_id, configuration):
    # Business-only text can enrich profiles without pretending to be an image-backed offer.
    if not publication_ready(db, configuration):
        return 0
    capture = db.get(ConversationCapture, capture_id)
    if not capture or not capture.acquisition.get("display_allowed"):
        return 0
    count = 0
    for version in db.scalars(
        select(PostVersion)
        .join(CaptureMember, CaptureMember.version_id == PostVersion.id)
        .where(CaptureMember.capture_id == capture_id)
    ):
        if (
            aware(version.retention_until) <= utcnow()
            or not seller_language(version.caption)
            or not location_language(version.caption)
        ):
            continue
        post = db.get(SourcePost, version.post_id)
        if post.access_state == "removed":
            continue
        account = db.get(SourceAccount, post.account_id)
        from .conversation_contracts import QuoteReference
        from .conversations import anchor_quote

        location = re.search(r"hà\s*nội|ha\s*noi|hanoi", version.caption, re.I)
        if not location:
            continue
        quote = version.caption[max(0, location.start() - 35) : location.end() + 35]
        try:
            reference = anchor_quote(db, QuoteReference(version_id=version.id, quote=quote))
        except ValueError:
            continue
        if not account.seller_id:
            seller = Seller(
                name=f"@{account.username}",
                slug=f"threads-{account.id}",
                district="Unknown",
                city="Hanoi",
                profile_url=f"https://www.threads.com/@{account.username}",
            )
            db.add(seller)
            db.flush()
            account.seller_id, account.role = seller.id, "seller"
        from types import SimpleNamespace

        entity = SimpleNamespace(seller_id=account.seller_id)
        seller_fact(db, entity, "service_area", "Hanoi", reference)
        result = extract_caption(version.caption)
        for field in ["delivery", "lead_days"]:
            value = getattr(result, field)
            if value.value is not None:
                ref = value.evidence_refs[0]
                seller_fact(
                    db,
                    entity,
                    field,
                    value.value,
                    anchor_quote(db, QuoteReference(version_id=version.id, quote=ref.quote)),
                )
        count += 1
    return count
