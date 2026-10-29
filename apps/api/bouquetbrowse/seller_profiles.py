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


def project_profile_snapshot(db, snapshot_id, configuration):
    """Only explicit public business lines; never promote a buyer's request to a seller."""
    from types import SimpleNamespace

    from .browser_models import ProfileSnapshot
    from .extraction import fold
    from .pilot import offer_configuration

    snapshot = db.get(ProfileSnapshot, snapshot_id)
    if (
        not snapshot
        or not snapshot.text
        or aware(snapshot.retention_until) <= utcnow()
        or not snapshot.policy.get("display_allowed")
        or not publication_ready(db, offer_configuration(configuration))
    ):
        return 0
    text = snapshot.text
    business = re.search(r"\b(?:florist|tiem hoa|shop hoa|flower studio|flower shop)\b", fold(text))
    if not business or not location_language(text):
        return 0
    account = db.get(SourceAccount, snapshot.account_id)
    if not account.seller_id:
        seller = Seller(
            name=f"@{account.username}",
            slug=f"threads-{account.id}",
            district="Unknown",
            city="Hanoi",
            profile_url=snapshot.source_url,
        )
        db.add(seller)
        db.flush()
        account.seller_id, account.role = seller.id, "seller"
    entity = SimpleNamespace(seller_id=account.seller_id)
    candidates = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 300 or text.count(line) != 1:
            continue
        normalized = fold(line)
        if re.search(r"\b(?:florist|tiem hoa|shop hoa|flower studio|flower shop)\b", normalized):
            candidates.append(("business_description", line, line))
        if location_language(line):
            candidates.append(("service_area", "Hanoi", line))
        # Public business contact only when explicitly labeled, not arbitrary profile numbers.
        if re.match(r"^(?:hotline|zalo|email|contact|lien he)\s*[:：]", normalized):
            candidates.append(("business_contact", line, line))
        result = extract_caption(line)
        for field in ["delivery", "lead_days"]:
            value = getattr(result, field)
            if value.value is not None:
                candidates.append((field, value.value, line))
    for field, value, quote in candidates:
        start = text.index(quote)
        seller_fact(
            db,
            entity,
            field,
            value,
            {"profile_snapshot_id": snapshot.id, "quote": quote, "start": start, "end": start + len(quote)},
        )
    return len(candidates)


def profile_summary(listings, facts):
    """A projection of visible catalog facts, never an inferred quality assessment."""
    flowers, styles = set(), set()
    for listing in listings:
        for component in listing.attributes.get("composition", []):
            if component.get("review_state") in {"accepted", "corrected"} and component.get("flower"):
                flowers.add(component["flower"])
        if listing.attributes.get("style"):
            styles.add(str(listing.attributes["style"]))
    services = sorted({f.field for f in facts if f.field in {"delivery", "lead_days", "service_area"}})
    count = len(listings)
    return {
        "vi": f"Đã ghi nhận {count} mẫu hoa trong danh mục. Hỏi người bán về tình trạng hiện tại.",
        "en": f"{count} bouquet offers observed in the catalog. Ask the seller about current availability.",
        "observed_flower_types": sorted(flowers),
        "observed_styles": sorted(styles),
        "stated_services": services,
    }


def project_business_capture(db, capture_id, configuration):
    # Business-only text can enrich profiles without pretending to be an image-backed offer.
    from .pilot import offer_configuration

    if not publication_ready(
        db, offer_configuration({**configuration, "prompt_version": "offer-text-v1", "schema_version": "offer-v1"})
    ):
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
