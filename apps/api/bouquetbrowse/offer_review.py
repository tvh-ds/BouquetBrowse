"""Human review creates a new revision; it cannot invent commercial evidence."""

from sqlalchemy import select

from .conversation_contracts import QuoteReference
from .conversation_models import OfferClaim, OfferOccurrence
from .conversations import anchor_quote
from .extraction import FLOWERS, extract_caption
from .models import ListingRevision, ReviewAction
from .offer_models import OfferAnalysis
from .offers import evidence_bundle
from .projection import project_offer
from .runtime_models import GraphExecution


def review_offer(db, listing, decision, actor):
    offer = db.scalar(select(OfferOccurrence).where(OfferOccurrence.listing_id == listing.id).with_for_update())
    if not offer or decision.expected_fingerprint != offer.input_fingerprint:
        raise ValueError("Offer evidence changed; reload its current fingerprint before reviewing")
    analysis = db.scalar(
        select(OfferAnalysis)
        .where(
            OfferAnalysis.offer_id == offer.id,
            OfferAnalysis.fingerprint == offer.input_fingerprint,
            OfferAnalysis.state == "completed",
        )
        .order_by(OfferAnalysis.created_at.desc())
        .limit(1)
    )
    if decision.decision == "reject":
        listing.state, offer.state = "rejected", "rejected"
    else:
        if not analysis or analysis.output.get("errors"):
            raise ValueError("Resolve association exceptions before commercial review")
        bundle = evidence_bundle(db, offer)
        output = dict(analysis.output)
        previous = db.get(ListingRevision, analysis.revision_id)
        fields = dict(previous.snapshot["fields"])
        for name in ["primary_flower", "color", "arrangement"]:
            value = getattr(decision, name)
            if value is not None:
                fields[name] = value
        if decision.stem_count is not None and decision.stem_count != fields.get("stem_count"):
            quote = decision.configuration_evidence_quote or ""
            source = next((m for m in bundle["messages"] if m["seller"] and quote and quote in m["text"]), None)
            if (
                not source
                or extract_caption(quote).stem_count.value != decision.stem_count
                or not any(word in quote.lower() for word in ["total", "tổng", "stems", "cành"])
            ):
                raise ValueError("A bouquet total requires an exact seller-stated total quote")
            anchor_quote(db, QuoteReference(version_id=source["version_id"], quote=quote))
            fields["stem_count"] = decision.stem_count
        if decision.price_minor is not None:
            matching = [
                p
                for p in output.get("prices", [])
                if p["amount_min"] == decision.price_minor
                and p["amount_max"] == decision.price_minor
                and p["kind"] in {"exact", "promotion"}
                and decision.price_evidence_quote == p["evidence"]["quote"]
            ]
            if len(matching) != 1:
                raise ValueError("Select one already bound exact monetary quote")
            output["prices"] = matching
        composition = list(output.get("composition", []))
        if decision.composition is not None:
            if set(decision.composition) - set(FLOWERS):
                raise ValueError("Review composition using curated florist types")
            composition = [
                {
                    "flower": flower,
                    "status": "visual_inference",
                    "evidence_refs": [],
                    "media_refs": [m["media_id"] for m in bundle["media"]],
                    "stated_count": next(
                        (
                            c.get("stated_count")
                            for c in composition
                            if c["flower"] == flower and c["status"] == "stated"
                        ),
                        None,
                    ),
                    "alternatives": [],
                    "review_state": "corrected",
                    "supported": False,
                    "review_actor": actor,
                }
                for flower in sorted(set(decision.composition))
            ]
        else:
            composition = [
                {
                    **c,
                    "review_state": "accepted"
                    if c.get("supported") and not c.get("alternatives")
                    else c.get("review_state", "pending"),
                }
                for c in composition
            ]
        output.update(
            composition=composition,
            commercial_reviewed=True,
            composition_reviewed=bool(composition)
            and all(c["review_state"] in {"accepted", "corrected"} and not c.get("alternatives") for c in composition),
        )
        revision = ListingRevision(
            listing_id=listing.id,
            snapshot={
                **previous.snapshot,
                "fields": fields,
                "composition": composition,
                "review_actor": actor,
                "previous_revision_id": previous.id,
                "published": False,
            },
            taxonomy_version=previous.taxonomy_version,
            pipeline_version="human-review-v1",
        )
        db.add(revision)
        db.flush()
        analysis.output, analysis.revision_id = output, revision.id
        listing.attributes = {
            **listing.attributes,
            "pending_offer_revision": revision.id,
            "size_reviewed": fields.get("stem_count") is not None,
        }
        for claim in db.scalars(select(OfferClaim).where(OfferClaim.offer_id == offer.id)):
            claim.review_state = "accepted"
        project_offer(db, offer, db.get(GraphExecution, analysis.execution_id), analysis)
    db.add(
        ReviewAction(
            listing_id=listing.id,
            actor=actor,
            decision=decision.decision,
            reason=decision.reason,
            changes={"submitted": decision.model_dump(mode="json"), "analysis_id": analysis.id if analysis else None},
        )
    )
    db.flush()
