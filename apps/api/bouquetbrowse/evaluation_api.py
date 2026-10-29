"""Admin-only annotation, explicit batch execution and private result export."""

from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User, require_admin
from .conversation_models import OfferOccurrence
from .db import aware, get_db, utcnow
from .evaluation import checked_item, judgments, queue_dataset
from .models import MediaAsset
from .pilot import offer_configuration, stage_proof
from .pipeline import digest, enqueue
from .research_models import EvaluationDataset, EvaluationItem
from .schemas import StrictModel
from .taxonomy import vocabulary

router = APIRouter(prefix="/v1/admin/evaluations", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(require_admin)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


class EvaluationSelection(StrictModel):
    offer_id: str
    media_id: str
    split: Literal["development", "holdout"]
    image_family: str = Field(min_length=1, max_length=160)


class DatasetBody(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    dataset_kind: Literal["synthetic", "permitted_real"] = "synthetic"
    items: list[EvaluationSelection] = Field(min_length=1, max_length=500)


class AnnotationBody(StrictModel):
    expected_version: int = Field(ge=1)
    labels: list[Annotated[str, Field(max_length=80)]] = Field(max_length=40)
    assessable: list[Annotated[str, Field(max_length=80)]] = Field(min_length=1, max_length=40)
    reviewers: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=1, max_length=5)
    split: Literal["development", "holdout"]
    image_family: str = Field(min_length=1, max_length=160)


class DatasetVersion(StrictModel):
    expected_version: int = Field(ge=1)


class ReferenceCommercial(StrictModel):
    prices: list[dict] = Field(max_length=30)
    claims: list[dict] = Field(max_length=30)


class ReferenceOffer(StrictModel):
    offer_id: str
    seller_account_id: str
    abstain: bool
    commercial_reference: ReferenceCommercial


class ReferenceConversation(StrictModel):
    capture_id: str
    pattern: Literal["seller_root", "buyer_request"]
    features: list[Literal["mixed", "multiple_sellers", "missing_price", "conflict", "partial"]]
    reviewers: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=2, max_length=5)
    offers: list[ReferenceOffer] = Field(min_length=1, max_length=30)


class ReferenceBatch(StrictModel):
    values: list[ReferenceConversation] = Field(min_length=1, max_length=40)


@router.post("/conversation-references")
def reference_signatures(body: ReferenceBatch):
    from .pilot import commercial_signature

    values = []
    for row in body.values:
        value = row.model_dump(mode="json")
        for offer in value["offers"]:
            offer["commercial_hash"] = commercial_signature(offer.pop("commercial_reference"))
        values.append(value)
    return {
        "values": values,
        "note": "Signatures of operator-supplied references; no model output was copied or judged automatically",
    }


def dataset_row(db, dataset_id, expected=None):
    row = db.scalar(select(EvaluationDataset).where(EvaluationDataset.id == dataset_id).with_for_update())
    if not row or aware(row.retention_until) <= utcnow() or expected is not None and row.version != expected:
        raise HTTPException(409, detail="Evaluation changed or expired; reload it")
    return row


@router.get("")
def datasets(db: Database):
    return {
        "items": [
            {"id": d.id, "name": d.name, "kind": d.dataset_kind, "version": d.version, "expires_at": d.retention_until}
            for d in db.scalars(
                select(EvaluationDataset)
                .where(EvaluationDataset.retention_until > utcnow())
                .order_by(EvaluationDataset.created_at.desc())
                .limit(50)
            )
        ]
    }


@router.post("")
def create_dataset(body: DatasetBody, db: Database, actor: Actor, idempotency_key: Key):
    from .discovery import settings_row

    receipt = enqueue(
        db,
        "evaluation-receipt",
        {"body_hash": digest(body.model_dump()), "actor": actor.id},
        f"evaluation:{idempotency_key}",
    )
    if receipt.result:
        return receipt.result
    dataset = EvaluationDataset(
        name=body.name,
        dataset_kind=body.dataset_kind,
        configuration=offer_configuration(settings_row(db).configuration),
        actor=actor.id,
        retention_until=utcnow() + timedelta(days=30),
    )
    db.add(dataset)
    db.flush()
    checksums = set()
    for selection in body.items:
        offer, asset = db.get(OfferOccurrence, selection.offer_id), db.get(MediaAsset, selection.media_id)
        if not offer or not asset or not asset.checksum or asset.checksum in checksums:
            raise HTTPException(422, detail="Choose distinct checksummed images associated with retained offers")
        checksums.add(asset.checksum)
        item = EvaluationItem(
            dataset_id=dataset.id,
            offer_id=offer.id,
            media_id=asset.id,
            offer_fingerprint=offer.input_fingerprint,
            checksum=asset.checksum,
            seller_group=offer.account_id,
            image_family=selection.image_family,
            split=selection.split,
            retention_until=min(aware(asset.retention_until or utcnow()), aware(dataset.retention_until)),
        )
        db.add(item)
        db.flush()
        try:
            _, bundle = checked_item(db, item)
            from .models import PostVersion

            item.retention_until = min(
                [
                    aware(item.retention_until),
                    *[aware(db.get(PostVersion, m["version_id"]).retention_until) for m in bundle["messages"]],
                ]
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
    receipt.state, receipt.result = "succeeded", {"id": dataset.id, "version": dataset.version}
    db.commit()
    return receipt.result


@router.get("/{dataset_id}")
def detail(dataset_id: str, db: Database):
    dataset = dataset_row(db, dataset_id)
    return {
        "id": dataset.id,
        "name": dataset.name,
        "kind": dataset.dataset_kind,
        "version": dataset.version,
        "configuration": dataset.configuration,
        "taxonomy": vocabulary(db, dataset.configuration["taxonomy_version"]),
        "items": [
            {
                "id": i.id,
                "offer_id": i.offer_id,
                "media_id": i.media_id,
                "version": i.version,
                "seller_group": i.seller_group,
                "image_family": i.image_family,
                "split": i.split,
                "labels": i.labels,
                "assessable": i.assessable,
                "reviewers": i.reviewers,
                "state": i.state,
                "execution_id": i.execution_id,
                "cost_microusd": i.cost_microusd,
                "latency_ms": i.latency_ms,
            }
            for i in db.scalars(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset.id))
        ],
    }


@router.post("/{dataset_id}/items/{item_id}/annotation")
def annotate(dataset_id: str, item_id: str, body: AnnotationBody, db: Database, actor: Actor):
    dataset = dataset_row(db, dataset_id)
    item = db.get(EvaluationItem, item_id)
    if not item or item.dataset_id != dataset.id or item.version != body.expected_version:
        raise HTTPException(409, detail="Annotation changed; reload before saving")
    checked_item(db, item)
    allowed = set(vocabulary(db, dataset.configuration["taxonomy_version"]))
    if set(body.labels) - set(body.assessable) or set(body.assessable) - allowed:
        raise HTTPException(422, detail="Use curated categories and mark positive labels assessable")
    item.history = [
        *item.history[-29:],
        {
            "version": item.version,
            "actor": actor.id,
            "labels": item.labels,
            "reviewers": item.reviewers,
            "at": utcnow().isoformat(),
        },
    ]
    item.labels, item.assessable, item.reviewers = (
        sorted(set(body.labels)),
        sorted(set(body.assessable)),
        sorted(set(body.reviewers)),
    )
    item.split, item.image_family = body.split, body.image_family
    item.version, dataset.version = item.version + 1, dataset.version + 1
    if item.state == "unannotated":
        item.state = "annotated"
    if dataset.proof_id:
        from .pilot_models import PilotProof

        db.get(PilotProof, dataset.proof_id).state = "revoked"
        dataset.proof_id = None
    db.commit()
    return {"id": item.id, "version": item.version, "dataset_version": dataset.version}


@router.post("/{dataset_id}/run")
def run(dataset_id: str, body: DatasetVersion, db: Database, idempotency_key: Key):
    dataset = dataset_row(db, dataset_id, body.expected_version)
    try:
        ids = queue_dataset(db, dataset)
        db.commit()
        return {"execution_ids": ids, "state": "queued", "note": "Evaluation cannot publish catalog content"}
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("/{dataset_id}/export")
def export(dataset_id: str, db: Database):
    import json

    dataset = dataset_row(db, dataset_id)
    try:
        values = judgments(db, dataset)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return Response(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="evaluation-{dataset.id}.jsonl"',
        },
    )


@router.post("/{dataset_id}/stage")
def stage(dataset_id: str, body: DatasetVersion, db: Database):
    dataset = dataset_row(db, dataset_id, body.expected_version)
    try:
        proof = stage_proof(db, "recognition", judgments(db, dataset), dataset.configuration, dataset.dataset_kind)
        dataset.proof_id = proof.id
        db.commit()
        return {"id": proof.id, "state": proof.state, "report": proof.report, "report_hash": proof.report_hash}
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
