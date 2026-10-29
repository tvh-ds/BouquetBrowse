"""Resolve advertisements by source structure, never by visual similarity alone."""

import re
from datetime import timedelta

from sqlalchemy import select

from .conversation_contracts import QuoteReference
from .conversation_models import (
    CaptureMember,
    ConversationCapture,
    MessageEdge,
    OfferAssociation,
    OfferClaim,
    OfferOccurrence,
)
from .conversations import anchor_quote, ensure_occurrence
from .db import aware, utcnow
from .executions import create_execution
from .extraction import FLOWERS, extract_caption, extract_prices, fold
from .models import (
    Listing,
    ListingRevision,
    ListingSource,
    MediaAsset,
    PostMedia,
    PostVersion,
    PriceObservation,
    Seller,
    SourceAccount,
    SourcePost,
)
from .offer_contracts import OfferInterpretation
from .offer_models import AssociationReview
from .pipeline import digest, enqueue, title_for
from .providers import CapabilityError
from .runtime_models import GraphExecution

OFFER_WORDS = re.compile(
    r"(?:nhan\s+(?:dat|lam)|(?:shop|tiem) (?:minh|em)|ben (?:minh|em)|nha (?:minh|em)|minh (?:ban|lam|co)|em (?:ban|lam|co)|san mau|co san|for sale|we (?:make|sell)|our bouquet)"
)
BUYER_WORDS = re.compile(
    r"(?:tim (?:shop|hoa|bo)|can (?:tim|mua)|xin (?:goi y|tu van)|ai (?:ban|co)|looking for|recommend|ngan sach|budget)"
)
HANOI = re.compile(r"\b(?:ha noi|hanoi)\b")
SERVICE = re.compile(r"(?:giao|ship|delivery|phuc vu|service|dia chi|address|shop|tiem|florist|tai|o)\b")
AFFIRM = re.compile(r"^(?:da[ ,.!]*|vang[ ,.!]*|yes[ ,.!]*|dung(?: roi)?[ ,.!]*|chinh xac[ ,.!]*)$", re.I)


def component_count(text, flower):
    pattern = FLOWERS.get(flower)
    if not pattern:
        return None
    matches = list(re.finditer(r"\b(\d{1,4})\s*(?:(?:cành|bông|stems?)\s*)?(?:" + pattern + r")", text, re.I))
    values = {int(match[1]) for match in matches}
    return values.pop() if len(values) == 1 else None


def seller_language(text):
    normalized = fold(text)
    return bool(OFFER_WORDS.search(normalized)) and not BUYER_WORDS.search(normalized)


def location_language(text):
    value = fold(text)
    return bool(HANOI.search(value) and SERVICE.search(value)) and not BUYER_WORDS.search(value)


def latest_version(db, post_id):
    return db.scalar(
        select(PostVersion)
        .where(PostVersion.post_id == post_id)
        .order_by(PostVersion.created_at.desc(), PostVersion.id.desc())
        .limit(1)
    )


def parent_id(db, post_id):
    parents = list(
        db.scalars(
            select(MessageEdge.target_id).where(MessageEdge.source_id == post_id, MessageEdge.kind == "reply_to")
        )
    )
    return parents[0] if len(parents) == 1 else None


def descendant_of(db, post_id, ancestor_id):
    seen = set()
    for _ in range(30):
        if post_id == ancestor_id:
            return True
        if not post_id or post_id in seen:
            return False
        seen.add(post_id)
        post_id = parent_id(db, post_id)
    return False


def current_associations(db, offer):
    return list(
        db.scalars(
            select(OfferAssociation)
            .where(OfferAssociation.offer_id == offer.id, OfferAssociation.revision == offer.association_revision)
            .order_by(OfferAssociation.version_id, OfferAssociation.item_key)
        )
    )


def offer_fingerprint(db, offer):
    refs = current_associations(db, offer)
    return digest(
        {
            "offer": offer.id,
            "kind": offer.kind,
            "associations": [(a.version_id, a.media_id, a.role, a.basis, a.region, a.state) for a in refs],
        }
    )


def register_media(db, version, policy):
    for position, url in enumerate(version.payload.get("media_urls", [])):
        link = db.scalar(select(PostMedia).where(PostMedia.version_id == version.id, PostMedia.position == position))
        if link:
            continue
        asset = MediaAsset(
            source_url=url, rights={**policy, "version_id": version.id}, retention_until=utcnow() + timedelta(days=90)
        )
        db.add(asset)
        db.flush()
        db.add(PostMedia(version_id=version.id, media_id=asset.id, position=position))
        enqueue(db, "prepare-media", {"media_id": asset.id}, f"media:{asset.id}")
    db.flush()


def exception(db, offer, kind, proposal=None):
    row = db.scalar(
        select(AssociationReview).where(
            AssociationReview.offer_id == offer.id,
            AssociationReview.fingerprint == offer.input_fingerprint,
            AssociationReview.kind == kind,
        )
    )
    if not row:
        row = AssociationReview(
            offer_id=offer.id, fingerprint=offer.input_fingerprint, kind=kind, proposal=proposal or {}
        )
        db.add(row)
        db.flush()
    return row


def segment_capture(db, capture_id, configuration):
    """Generate bounded candidates. Interpretation and publication remain separate gates."""
    capture = db.get(ConversationCapture, capture_id)
    if not capture or aware(capture.retention_until) <= utcnow() or not capture.acquisition.get("processing_allowed"):
        raise CapabilityError("Capture evidence is unavailable.", "source_expired")
    versions = list(
        db.scalars(
            select(PostVersion)
            .join(CaptureMember, CaptureMember.version_id == PostVersion.id)
            .where(CaptureMember.capture_id == capture_id)
        )
    )
    # Latest observations for each global message; a stale capture cannot roll them back.
    versions = {v.post_id: latest_version(db, v.post_id) for v in versions}
    # A reply-only refresh must also invalidate/rebuild its known ancestor offers.
    for observed_id in list(versions):
        ancestor, visited = parent_id(db, observed_id), set()
        for _ in range(30):
            if not ancestor or ancestor in visited:
                break
            visited.add(ancestor)
            version = latest_version(db, ancestor)
            if version and aware(version.retention_until) > utcnow():
                versions[ancestor] = version
            ancestor = parent_id(db, ancestor)
    candidates = []
    for post_id, version in versions.items():
        post = db.get(SourcePost, post_id)
        account = db.get(SourceAccount, post.account_id)
        if post.access_state == "removed" or not version.caption:
            continue
        images = version.payload.get("media_urls", [])
        recreation = bool(re.search(r"(?:lam|recreate|recreation|dat).*(?:mau|theo|reference)", fold(version.caption)))
        if not images and not recreation:
            continue
        # Candidate-only: neither image ownership nor seller status is established by this sweep.
        existing = list(
            db.scalars(
                select(OfferOccurrence).where(
                    OfferOccurrence.account_id == account.id, OfferOccurrence.anchor_id == post.id
                )
            )
        )
        offer = (
            existing[0]
            if len(existing) == 1
            else ensure_occurrence(db, account.id, post.id, kind="recreation_quote" if recreation else "seller_work")
        )
        anchor_versions = {post.id: version}
        pending, seen = [post.id], {post.id}
        for _ in range(30):
            children = (
                list(
                    db.scalars(
                        select(MessageEdge.source_id)
                        .where(MessageEdge.kind == "reply_to", MessageEdge.target_id.in_(pending))
                        .limit(41)
                    )
                )
                if pending
                else []
            )
            pending = []
            for child in children:
                if child in seen or len(seen) >= 40:
                    continue
                seen.add(child)
                pending.append(child)
                current = latest_version(db, child)
                if current and current.caption and aware(current.retention_until) > utcnow():
                    anchor_versions[child] = current
            if not pending:
                break
        if recreation:
            parent = parent_id(db, post.id)
            if parent:
                reference = latest_version(db, parent)
                if reference and aware(reference.retention_until) > utcnow():
                    anchor_versions[parent] = reference
        desired = []
        for source_id, evidence_version in anchor_versions.items():
            source = db.get(SourcePost, source_id)
            role = "seller_message" if source.account_id == account.id else "buyer_context"
            desired.append((evidence_version.id, None, role, "reply_ancestry", "message"))
            if source_id == post.id or recreation and source_id == parent_id(db, post.id):
                register_media(db, evidence_version, capture.acquisition)
                for media in db.scalars(select(PostMedia).where(PostMedia.version_id == evidence_version.id)):
                    desired.append(
                        (
                            evidence_version.id,
                            media.media_id,
                            "seller_image" if source_id == post.id else "reference_image",
                            "source_author",
                            f"image:{media.position}",
                        )
                    )
        previous = [(a.version_id, a.media_id, a.role, a.basis, a.item_key) for a in current_associations(db, offer)]
        if sorted(previous, key=str) != sorted(desired, key=str):
            if previous:
                offer.association_revision += 1
            for version_id, media_id, role, basis, item_key in desired:
                db.add(
                    OfferAssociation(
                        offer_id=offer.id,
                        revision=offer.association_revision,
                        version_id=version_id,
                        media_id=media_id,
                        role=role,
                        basis=basis,
                        item_key=item_key,
                        state="candidate",
                        evidence={"capture_id": capture.id},
                    )
                )
            db.flush()
            offer.input_fingerprint = offer_fingerprint(db, offer)
            if offer.listing_id:
                listing = db.get(Listing, offer.listing_id)
                listing.attributes = {**listing.attributes, "updating": True}
            offer.state = "candidate"
        config = {**configuration, "budget_usd": 0.10, "prompt_version": "offer-text-v1", "schema_version": "offer-v1"}
        config.pop("source_capture_id", None)
        config.pop("manual", None)
        config.pop("slot", None)
        from .graphs import BEHAVIOR_VERSION

        key = digest([offer.input_fingerprint, config, BEHAVIOR_VERSION])
        execution = create_execution(db, "offer", f"{offer.id}:{key}", config, offer.input_fingerprint, offer.id)
        for previous_execution in db.scalars(
            select(GraphExecution).where(
                GraphExecution.offer_id == offer.id,
                GraphExecution.id != execution.id,
                GraphExecution.state.in_(["queued", "running", "review", "paused"]),
            )
        ):
            previous_execution.state, previous_execution.stop_reason = "superseded", "new_offer_execution"
        candidates.append(execution.id)
    return candidates


def evidence_bundle(db, offer):
    associations = current_associations(db, offer)
    if not associations:
        raise CapabilityError("Offer associations are missing.", "association_unresolved")
    messages, remaining = [], 24000
    for version_id in sorted({a.version_id for a in associations}):
        version = db.get(PostVersion, version_id)
        post = db.get(SourcePost, version.post_id)
        if aware(version.retention_until) <= utcnow() or not version.caption or post.access_state == "removed":
            raise CapabilityError("Offer evidence expired or was removed.", "source_expired")
        # Newer relevant content must invalidate the old execution even before segmentation reruns.
        if latest_version(db, post.id).id != version.id:
            raise CapabilityError("Offer inputs changed during processing.", "stale_offer")
        excerpt = version.caption[: min(6000, max(0, remaining))]
        remaining -= len(excerpt)
        messages.append(
            {
                "version_id": version.id,
                "post_id": post.id,
                "account_id": post.account_id,
                "seller": post.account_id == offer.account_id,
                "parent_id": parent_id(db, post.id),
                "text": excerpt,
                "truncated": len(excerpt) < len(version.caption),
            }
        )
    return {
        "offer_id": offer.id,
        "anchor_id": offer.anchor_id,
        "kind": offer.kind,
        "messages": messages,
        "media": [
            {"media_id": a.media_id, "version_id": a.version_id, "role": a.role, "region": a.region}
            for a in associations
            if a.media_id
        ],
    }


def validate_interpretation(db, offer, result: OfferInterpretation):
    bundle = evidence_bundle(db, offer)
    by_version = {m["version_id"]: m for m in bundle["messages"]}
    errors, claims = [], []
    if any(m["truncated"] for m in bundle["messages"]):
        errors.append("context_truncated")
    account = db.get(SourceAccount, offer.account_id)

    def seller_quote(ref):
        anchored = anchor_quote(db, ref)
        if ref.version_id not in by_version or not by_version[ref.version_id]["seller"]:
            raise ValueError("Seller evidence must be authored by this offer's account")
        return anchored

    ownership = seller_quote(result.ownership) if result.ownership else None
    if (
        not result.seller_offer
        or not ownership
        or not seller_language(ownership["quote"])
        or not seller_language(by_version[ownership["version_id"]]["text"])
    ):
        errors.append("seller_ownership_unresolved")
    location = seller_quote(result.location) if result.location else None
    if not (
        location
        and location_language(location["quote"])
        and location_language(by_version[location["version_id"]]["text"])
    ) and not account.capabilities.get("location_reviewed"):
        errors.append("hanoi_service_unresolved")
    if result.multi_product:
        errors.append("multi_product_review")
    if not bundle["media"]:
        errors.append("image_association_unresolved")
    for field in result.fields:
        if field.field in {"ownership", "location"}:
            continue
        if field.derivation == "seller_confirmation":
            if len(field.evidence) != 2 or field.field not in {
                "stem_count",
                "flower_count",
                "lead_days",
                "delivery",
                "flower",
            }:
                raise ValueError("Unsupported seller-confirmation derivation")
            question, answer = field.evidence
            q, a = by_version.get(question.version_id), by_version.get(answer.version_id)
            if (
                not q
                or not a
                or q["seller"]
                or not a["seller"]
                or a["parent_id"] != q["post_id"]
                or not descendant_of(db, q["post_id"], offer.anchor_id)
            ):
                raise ValueError("Confirmation must directly answer an offer-bound buyer question")
            # Reject compound/negative questions, multiple propositions and non-affirmative answers.
            if (
                q["text"].count("?") != 1
                or re.search(r"\b(?:khong|not|hay|or|va|and)\b", fold(q["text"]))
                or len(re.findall(r"\d+", q["text"])) > 1
                or not AFFIRM.fullmatch(fold(a["text"]).strip())
            ):
                raise ValueError("Ambiguous confirmation requires review")
            refs = [anchor_quote(db, question), seller_quote(answer)]
            parsed = extract_caption(question.quote)
        else:
            refs = [seller_quote(ref) for ref in field.evidence]
            if any(
                re.search(r"\b(?:khong|not|chua|khong phai)\b", fold(by_version[r["version_id"]]["text"])) for r in refs
            ):
                raise ValueError("Negated seller claims require review")
            parsed = extract_caption(" ".join(r["quote"] for r in refs))
        if field.field == "flower_count":
            if not field.flower or field.flower not in (parsed.flower_composition.value or []):
                raise ValueError("Component counts require a supported flower type")
            expected = component_count(
                question.quote if field.derivation == "seller_confirmation" else " ".join(ref["quote"] for ref in refs),
                field.flower,
            )
        else:
            expected = (
                parsed.flower_composition.value or [] if field.field == "flower" else getattr(parsed, field.field).value
            )
        if field.field == "stem_count" and not re.search(
            r"(?:total|tong|stems?\b|canh\b)", fold(" ".join(ref["quote"] for ref in refs))
        ):
            raise ValueError("A flower component count is not a bouquet total")
        if (
            field.field == "stem_count"
            and any(
                len(extract_caption(by_version[ref["version_id"]]["text"]).flower_composition.value or []) > 1
                for ref in refs
            )
            and not re.search(r"\b(?:total|tong)\b", fold(" ".join(ref["quote"] for ref in refs)))
        ):
            raise ValueError("Mixed bouquet totals require explicit total wording")
        if (
            field.value not in expected
            if field.field == "flower"
            else type(field.value) is not type(expected) or field.value != expected
        ):
            raise ValueError("Claim value is unsupported by its evidence")
        claims.append(
            {
                "field": field.field,
                "value": {"value": field.value, **({"flower": field.flower} if field.field == "flower_count" else {})},
                "evidence": refs,
                "status": "stated",
                "derivation": field.derivation,
            }
        )
    # Commercial prices are parsed on the actual seller message, and must bind to this unique offer.
    prices = []
    for message in bundle["messages"]:
        if not message["seller"]:
            continue
        targets = [
            o
            for o in db.scalars(select(OfferOccurrence).where(OfferOccurrence.account_id == offer.account_id))
            if descendant_of(db, message["post_id"], o.anchor_id)
        ]
        # A newer offer in the ancestry overrides a root offer. Sibling/root price guesses never bind.
        nearest = [
            o
            for o in targets
            if not any(
                other.id != o.id and other.anchor_id != o.anchor_id and descendant_of(db, other.anchor_id, o.anchor_id)
                for other in targets
            )
        ]
        parsed, warnings = extract_prices(message["text"])
        bouquet_prices = [p for p in parsed if p.component == "bouquet" and p.kind != "previous"]
        if len(nearest) != 1 or nearest[0].id != offer.id or len(bouquet_prices) > 1 or warnings:
            if bouquet_prices:
                errors.append("commercial_target_unresolved")
            continue
        if re.search(r"\b(?:khong|not|budget|ngan sach)\b|\?", fold(message["text"])):
            continue
        post = db.get(SourcePost, message["post_id"])
        for price in bouquet_prices:
            ref = anchor_quote(db, QuoteReference(version_id=message["version_id"], quote=price.evidence.quote))
            prices.append(
                {
                    **price.model_dump(mode="json"),
                    "version_id": message["version_id"],
                    "evidence": ref,
                    "advertised_at": post.published_at.isoformat() if post.published_at else None,
                }
            )
    if len({(p["amount_min"], p["amount_max"], p["currency"]) for p in prices}) > 1:
        errors.append("conflicting_prices")
    composition = []
    for claim in claims:
        if claim["field"] in {"flower", "flower_count"}:
            flower = claim["value"].get("flower") or claim["value"]["value"]
            component = next((c for c in composition if c["flower"] == flower), None)
            if component is None:
                component = {
                    "flower": flower,
                    "status": "stated",
                    "evidence_refs": [],
                    "media_refs": [],
                    "stated_count": None,
                    "alternatives": [],
                    "review_state": "pending",
                    "supported": True,
                }
                composition.append(component)
            component["evidence_refs"].extend(claim["evidence"])
            if claim["field"] == "flower_count":
                if component["stated_count"] not in {None, claim["value"]["value"]}:
                    errors.append("conflicting_component_counts")
                    component["status"] = "conflict"
                else:
                    component["stated_count"] = claim["value"]["value"]
    return {
        "claims": claims,
        "prices": prices,
        "ownership": ownership,
        "location": location,
        "errors": sorted(set(errors)),
        "warnings": result.warnings,
        "composition": composition,
    }


def commit_offer(db, offer, execution, output):
    """Atomic revision command; no source/model calls and no mutation of identity."""
    from .offer_models import OfferAnalysis

    analysis = db.scalar(select(OfferAnalysis).where(OfferAnalysis.execution_id == execution.id))
    if analysis.revision_id:
        return analysis.revision_id
    if offer.input_fingerprint != analysis.fingerprint or offer_fingerprint(db, offer) != analysis.fingerprint:
        raise CapabilityError("Newer evidence supersedes this extraction.", "stale_offer")
    evidence_bundle(db, offer)
    if output["errors"]:
        for kind in output["errors"]:
            exception(db, offer, kind)
        offer.state, analysis.state = "review", "review"
        return None
    account = db.get(SourceAccount, offer.account_id)
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
    offer.seller_id = account.seller_id
    listing = db.get(Listing, offer.listing_id) if offer.listing_id else None
    if listing and listing.state in {"withdrawn", "rejected"}:
        raise CapabilityError("Suppressed offer cannot be republished.", "source_removed")
    fields = {
        c["field"]: c["value"]["value"]
        for c in output["claims"]
        if c["field"] in {"arrangement", "color", "stem_count"}
    }
    flowers = sorted(
        {c["flower"] for c in output.get("composition", []) if c.get("supported") and not c.get("alternatives")}
    )
    fields["primary_flower"] = "mixed" if len(flowers) > 1 else next(iter(flowers), None)
    if not listing:
        listing = Listing(
            seller_id=offer.seller_id,
            configuration_key=digest(["occurrence", offer.id]),
            title=title_for(fields),
            description="",
            attributes={},
            search_text="",
            state="review",
        )
        db.add(listing)
        db.flush()
        offer.listing_id = listing.id
    for claim in output["claims"]:
        previous = db.scalar(
            select(OfferClaim)
            .where(OfferClaim.offer_id == offer.id, OfferClaim.field == claim["field"])
            .order_by(OfferClaim.observed_at.desc())
            .limit(1)
        )
        source = db.get(SourcePost, db.get(PostVersion, claim["evidence"][-1]["version_id"]).post_id)
        db.add(
            OfferClaim(
                offer_id=offer.id,
                field=claim["field"],
                value={**claim["value"], "derivation": claim["derivation"]},
                evidence=claim["evidence"],
                status=claim["status"],
                valid_from=source.published_at,
                supersedes_id=previous.id if previous else None,
                method_version=execution.behavior_version,
            )
        )
    for association in current_associations(db, offer):
        if not db.scalar(
            select(ListingSource.id).where(
                ListingSource.listing_id == listing.id, ListingSource.version_id == association.version_id
            )
        ):
            db.add(ListingSource(listing_id=listing.id, version_id=association.version_id))
            db.flush()
    for price in output["prices"]:
        if not price["advertised_at"]:
            continue  # Unknown source date is never replaced by discovery time.
        if not db.scalar(
            select(PriceObservation.id).where(
                PriceObservation.listing_id == listing.id,
                PriceObservation.version_id == price["version_id"],
                PriceObservation.amount_min == price["amount_min"],
                PriceObservation.amount_max == price["amount_max"],
            )
        ):
            from datetime import datetime

            db.add(
                PriceObservation(
                    listing_id=listing.id,
                    version_id=price["version_id"],
                    amount_min=price["amount_min"],
                    amount_max=price["amount_max"],
                    currency=price["currency"],
                    kind=price["kind"],
                    component="bouquet",
                    reviewed=False,
                    evidence={**price["evidence"], "currency_basis": price["currency_basis"], "offer_id": offer.id},
                    advertised_at=datetime.fromisoformat(price["advertised_at"]),
                )
            )
    snapshot = {
        "title": title_for(fields),
        "fields": fields,
        "composition": output.get("composition", []),
        "warnings": output["warnings"],
        "offer_type": offer.kind,
        "fingerprint": analysis.fingerprint,
        "evidence_at": utcnow().isoformat(),
    }
    revision = ListingRevision(
        listing_id=listing.id,
        snapshot=snapshot,
        taxonomy_version=execution.configuration.get("taxonomy_version", "flowers-v2"),
        pipeline_version=execution.behavior_version,
    )
    db.add(revision)
    db.flush()
    # Module 15 supplies gated projection into the public-facing catalog.
    listing.attributes = {**listing.attributes, "pending_offer_revision": revision.id, "offer_id": offer.id}
    analysis.revision_id, analysis.state, offer.state = revision.id, "completed", "validated"
    return revision.id
