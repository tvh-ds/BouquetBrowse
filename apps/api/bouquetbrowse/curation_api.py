"""Version-checked, audited curation without changing stable offer/listing identity."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User, require_admin
from .conversation_models import CanonicalConfiguration, CanonicalLink, OfferOccurrence, TaxonomyTerm
from .conversations import link_canonical
from .db import get_db
from .pipeline import digest, enqueue
from .schemas import StrictModel
from .taxonomy import promote, vocabulary

router = APIRouter(prefix="/v1/admin/curation", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(require_admin)]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


def fingerprint(row):
    return digest(
        {
            "id": row.id,
            "state": row.state,
            "evidence": getattr(row, "evidence", None),
            "evaluation": getattr(row, "evaluation", None),
            "aliases": getattr(row, "aliases", None),
        }
    )


def command(db, key, body, actor):
    payload = {"request_hash": digest(body.model_dump(mode="json")), "actor": actor}
    row = enqueue(db, "curation-receipt", payload, f"curation:{key}")
    if row.result:
        return row, row.result
    row.state = "succeeded"  # In the same transaction as the decision, never worker-executed.
    return row, None


class TaxonomyDecision(StrictModel):
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["promote", "reject"]
    new_version: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    aliases: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=30)
    canonical_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,79}$")
    reason: str = Field(min_length=10, max_length=500)


class CanonicalDecision(StrictModel):
    offer_id: str
    expected_fingerprint: str
    expected_links_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_id: str | None = None
    reason: str = Field(min_length=10, max_length=500)


class UnlinkDecision(StrictModel):
    expected_fingerprint: str
    reason: str = Field(min_length=10, max_length=500)


def links_hash(db, offer_id):
    return digest(
        sorted(
            fingerprint(link) for link in db.scalars(select(CanonicalLink).where(CanonicalLink.offer_id == offer_id))
        )
    )


@router.post("/profiles/{account_id}/remove")
def remove_business_profile(account_id: str, db: Database, actor: Actor, idempotency_key: CommandKey):
    from .models import SourceAccount
    from .retention import remove_profile

    if not db.get(SourceAccount, account_id):
        raise HTTPException(404, detail="Profile account not found")
    remove_profile(db, account_id)
    db.commit()
    return {"account_id": account_id, "state": "removed"}


@router.get("/taxonomy")
def terms(db: Database):
    from .discovery import settings_row

    version = settings_row(db).configuration.get("taxonomy_version", "flowers-v2")
    return {
        "version": version,
        "vocabulary": vocabulary(db, version),
        "items": [
            {
                "id": r.id,
                "key": r.key,
                "version": r.taxonomy_version,
                "state": r.state,
                "aliases": r.aliases,
                "fingerprint": fingerprint(r),
                "evaluation": r.evaluation,
            }
            for r in db.scalars(select(TaxonomyTerm).order_by(TaxonomyTerm.created_at.desc()).limit(200))
        ],
    }


@router.post("/taxonomy/{term_id}/decision")
def decide_term(term_id: str, body: TaxonomyDecision, db: Database, actor: Actor, idempotency_key: CommandKey):
    try:
        receipt, previous = command(db, idempotency_key, body, actor.id)
        if previous:
            return previous
        row = db.scalar(select(TaxonomyTerm).where(TaxonomyTerm.id == term_id).with_for_update())
        if not row or fingerprint(row) != body.expected_fingerprint or row.state != "proposed":
            raise ValueError("Proposal changed; reload before deciding")
        if body.decision == "promote":
            version = promote(db, row, body.new_version, body.aliases, actor.id, body.reason, body.canonical_key)
        else:
            row.state, row.evaluation = "rejected", {**row.evaluation, "actor": actor.id, "reason": body.reason}
            version = row.taxonomy_version
        receipt.result = {"id": row.id, "state": row.state, "version": version}
        db.commit()
        return receipt.result
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("/canonical")
def canonical(db: Database):
    return {
        "configurations": [
            {"id": c.id, "seller_id": c.seller_id} for c in db.scalars(select(CanonicalConfiguration).limit(200))
        ],
        "offers": [
            {
                "id": o.id,
                "seller_id": o.seller_id,
                "listing_id": o.listing_id,
                "fingerprint": o.input_fingerprint,
                "links_hash": links_hash(db, o.id),
            }
            for o in db.scalars(
                select(OfferOccurrence)
                .where(
                    OfferOccurrence.seller_id.is_not(None),
                    OfferOccurrence.state.not_in(["withdrawn", "expired", "rejected"]),
                )
                .limit(200)
            )
        ],
        "links": [
            {
                "id": link.id,
                "offer_id": link.offer_id,
                "configuration_id": link.configuration_id,
                "state": link.state,
                "fingerprint": fingerprint(link),
            }
            for link in db.scalars(select(CanonicalLink).limit(500))
        ],
    }


@router.post("/canonical/link")
def consolidate(body: CanonicalDecision, db: Database, actor: Actor, idempotency_key: CommandKey):
    try:
        receipt, previous = command(db, idempotency_key, body, actor.id)
        if previous:
            return previous
        offer = db.scalar(select(OfferOccurrence).where(OfferOccurrence.id == body.offer_id).with_for_update())
        if (
            not offer
            or offer.input_fingerprint != body.expected_fingerprint
            or not offer.seller_id
            or offer.state in {"withdrawn", "expired", "rejected"}
        ):
            raise ValueError("Offer changed or is unavailable")
        evidence = {"actor": actor.id, "reason": body.reason, "offer_fingerprint": offer.input_fingerprint}
        if links_hash(db, offer.id) != body.expected_links_hash:
            raise ValueError("Canonical relationships changed; reload before linking")
        configuration = db.get(CanonicalConfiguration, body.configuration_id) if body.configuration_id else None
        if body.configuration_id and (not configuration or not configuration.evidence):
            raise ValueError("Configuration not found")
        if not configuration:
            configuration = CanonicalConfiguration(seller_id=offer.seller_id, evidence=evidence)
            db.add(configuration)
            db.flush()
        link = link_canonical(db, offer.id, configuration.id, "reviewed_match", evidence)
        for prior in db.scalars(
            select(CanonicalLink).where(CanonicalLink.offer_id == offer.id, CanonicalLink.state == "accepted")
        ):
            if prior is not link:
                prior.state = "superseded"
        db.flush()
        receipt.result = {"link_id": link.id, "configuration_id": configuration.id, "offer_id": offer.id}
        db.commit()
        return receipt.result
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.post("/canonical/{link_id}/unlink")
def unlink(link_id: str, body: UnlinkDecision, db: Database, actor: Actor, idempotency_key: CommandKey):
    try:
        receipt, previous = command(db, idempotency_key, body, actor.id)
        if previous:
            return previous
        link = db.scalar(select(CanonicalLink).where(CanonicalLink.id == link_id).with_for_update())
        if not link or fingerprint(link) != body.expected_fingerprint or link.state != "accepted":
            raise ValueError("Canonical link changed; reload before deciding")
        link.state, link.evidence = (
            "revoked",
            {**link.evidence, "revoked_by": actor.id, "revocation_reason": body.reason},
        )
        receipt.result = {"link_id": link.id, "state": link.state}
        db.commit()
        return receipt.result
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
