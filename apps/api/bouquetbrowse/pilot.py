"""Recompute release evidence locally; never run a model or trust supplied metrics."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select

from .conversation_models import CaptureMember, ConversationCapture, OfferAssociation, OfferOccurrence
from .db import aware, utcnow
from .graphs import BEHAVIOR_VERSION
from .models import AppUser, MediaAsset, PostVersion, SourcePost
from .offer_models import OfferAnalysis
from .pilot_models import PilotProof
from .pipeline import digest
from .recognition import configuration_hash
from .recognition_evaluation import ImageJudgment, evaluate_images
from .recognition_models import RecognitionRecord, RecognitionSupport
from .runtime_models import GraphExecution
from .schemas import StrictModel


def offer_configuration(configuration=None):
    from .config import get_settings

    settings = get_settings()
    return {
        "extraction_model": settings.extraction_model,
        "escalation_model": settings.escalation_model,
        "taxonomy_version": "flowers-v2",
        "recognition_version": "mixed-flowers-v1",
        "preprocessing_version": "jpeg-1200-v1",
        "image_embedding_provider": settings.image_embedding_provider,
        "siglip_revision": settings.siglip_revision,
        "prompt_version": "offer-text-v1",
        "schema_version": "offer-v1",
        **(configuration or {}),
    }


class ExpectedOffer(StrictModel):
    offer_id: str
    seller_account_id: str
    abstain: bool
    # Exact, reviewed commercial signatures. Evidence references include both messages
    # for confirmations. Amount/currency/basis changes fail equality, not just a score.
    commercial_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConversationJudgment(StrictModel):
    capture_id: str
    pattern: Literal["seller_root", "buyer_request"]
    features: list[Literal["mixed", "multiple_sellers", "missing_price", "conflict", "partial"]]
    offers: list[ExpectedOffer] = Field(min_length=1, max_length=30)
    reviewers: list[str] = Field(min_length=2, max_length=5)


def commercial_signature(output):
    return digest(
        {
            "prices": output.get("prices", []),
            "claims": [
                c
                for c in output.get("claims", [])
                if c["field"] in {"stem_count", "flower_count", "lead_days", "delivery"}
            ],
        }
    )


def evaluate_conversations(db, values, configuration, dataset_kind):
    rows = [ConversationJudgment.model_validate(value) for value in values]
    if len({r.capture_id for r in rows}) != len(rows):
        raise ValueError("Conversation proof requires distinct captures")
    failures, dependencies, patterns, features = [], set(), {"seller_root": 0, "buyer_request": 0}, set()
    seen_offers, roots = set(), set()
    positives, abstentions = {"seller_root": 0, "buyer_request": 0}, 0
    config_hash = configuration_hash(configuration)
    for row in rows:
        if len(set(row.reviewers)) < 2:
            raise ValueError("Reference interpretations need two distinct reviewers")
        capture = db.get(ConversationCapture, row.capture_id)
        if not capture or aware(capture.retention_until) <= utcnow():
            raise ValueError("Conversation evidence is missing or expired")
        if capture.source_url in roots:
            raise ValueError("Repeated captures of one conversation are not distinct cases")
        roots.add(capture.source_url)
        patterns[row.pattern] += 1
        features.update(row.features)
        versions = set(db.scalars(select(CaptureMember.version_id).where(CaptureMember.capture_id == capture.id)))
        dependencies.update(versions)
        candidates = set(db.scalars(select(OfferAssociation.offer_id).where(OfferAssociation.version_id.in_(versions))))
        expected = {o.offer_id for o in row.offers}
        if len(expected) != len(row.offers) or expected & seen_offers:
            raise ValueError("Each offer is judged once in a reference proof")
        seen_offers.update(expected)
        for offer_id in candidates - expected:
            offer = db.get(OfferOccurrence, offer_id)
            if offer.state not in {"rejected", "split", "withdrawn"}:
                failures.append("unjudged_candidate")
        for reference in row.offers:
            positives[row.pattern] += int(not reference.abstain)
            abstentions += int(reference.abstain)
            offer = db.get(OfferOccurrence, reference.offer_id)
            if not offer or offer.id not in candidates or offer.account_id != reference.seller_account_id:
                failures.append("wrong_seller_or_unbound_offer")
                continue
            analysis = db.scalar(
                select(OfferAnalysis)
                .join(GraphExecution, GraphExecution.id == OfferAnalysis.execution_id)
                .where(
                    OfferAnalysis.offer_id == offer.id,
                    OfferAnalysis.fingerprint == offer.input_fingerprint,
                    GraphExecution.behavior_version == BEHAVIOR_VERSION,
                )
                .order_by(OfferAnalysis.created_at.desc())
                .limit(1)
            )
            execution = db.get(GraphExecution, analysis.execution_id) if analysis else None
            if not analysis or configuration_hash(execution.configuration) != config_hash:
                failures.append("missing_current_analysis")
                continue
            abstained = bool(analysis.errors or analysis.output.get("errors") or analysis.state != "completed")
            if abstained != reference.abstain:
                failures.append("incorrect_abstention")
            if not reference.abstain and commercial_signature(analysis.output) != reference.commercial_hash:
                failures.append("unsupported_or_missing_commercial_binding")
    ready = (
        dataset_kind == "permitted_real"
        and len(rows) >= 20
        and min(patterns.values()) >= 10
        and min(positives.values()) > 0
        and abstentions > 0
        and not failures
        and features >= {"mixed", "multiple_sellers", "missing_price", "conflict", "partial"}
    )
    return {
        "schema_version": "conversation-proof-v1",
        "dataset_kind": dataset_kind,
        "conversations": len(rows),
        "patterns": patterns,
        "features": sorted(features),
        "non_abstaining": positives,
        "abstentions": abstentions,
        "failures": failures,
        "dataset_ready": ready,
    }, {"versions": sorted(dependencies)}


def evidence_current(db, dependencies):
    for record_id in dependencies.get("recognition_records", []):
        record = db.get(RecognitionRecord, record_id)
        if not record or not record.result or aware(record.retention_until) <= utcnow():
            return False
    for version_id in dependencies.get("versions", []):
        version = db.get(PostVersion, version_id)
        post = db.get(SourcePost, version.post_id) if version else None
        if not version or aware(version.retention_until) <= utcnow() or not post or post.access_state == "removed":
            return False
    for media_id in dependencies.get("media", []):
        asset = db.get(MediaAsset, media_id)
        if not asset or asset.state != "ready" or not asset.retention_until or aware(asset.retention_until) <= utcnow():
            return False
    return True


def stage_proof(db, kind, values, configuration, dataset_kind="synthetic"):
    if dataset_kind not in {"synthetic", "permitted_real"}:
        raise ValueError("Record dataset provenance explicitly")
    if configuration is None:
        from .discovery import settings_row

        configuration = settings_row(db).configuration
    configuration = offer_configuration(configuration)
    key = configuration_hash(configuration)
    if kind == "conversation":
        report, dependencies = evaluate_conversations(db, values, configuration, dataset_kind)
    elif kind == "recognition":
        from .taxonomy import vocabulary

        report = evaluate_images(values, key, dataset_kind, vocabulary(db, configuration["taxonomy_version"]))
        media_ids = []
        record_ids = []
        for value in values:
            row = ImageJudgment.model_validate(value)
            asset = db.get(MediaAsset, row.image_id)
            if not asset or asset.checksum != row.checksum:
                raise ValueError("Recognition judgments must reference retained checksummed source images")
            media_ids.append(asset.id)
            if dataset_kind == "permitted_real":
                for purpose, record_id, predictions in [
                    ("joint", row.joint_record_id, row.joint_predictions),
                    ("image_only", row.image_only_record_id, row.image_only_predictions),
                ]:
                    record = db.get(RecognitionRecord, record_id) if record_id else None
                    if (
                        not record
                        or record.purpose != purpose
                        or record.configuration_hash != key
                        or aware(record.retention_until) <= utcnow()
                    ):
                        raise ValueError("Real predictions need matching retained joint and image-only model receipts")
                    view_ids = {
                        v["view_id"]
                        for v in record.dependencies.get("views", [])
                        if v["media_id"] == asset.id and v["checksum"] == asset.checksum
                    }
                    actual = {
                        f["flower"]
                        for f in record.result.get("flowers", [])
                        if f.get("state") == "present"
                        and not f.get("alternatives")
                        and set(f.get("view_ids", [])) & view_ids
                    }
                    if not view_ids or actual != set(predictions):
                        raise ValueError("Image predictions do not match the stored image-specific recognition receipt")
                    record_ids.append(record.id)
        dependencies = {"media": sorted(media_ids), "recognition_records": sorted(set(record_ids))}
    else:
        raise ValueError("Unknown pilot proof kind")
    report = {
        **report,
        "configuration_hash": key,
        "behavior_version": BEHAVIOR_VERSION,
        "taxonomy_version": configuration["taxonomy_version"],
    }
    dataset_hash = digest(values)
    existing = db.scalar(
        select(PilotProof).where(
            PilotProof.kind == kind, PilotProof.configuration_hash == key, PilotProof.dataset_hash == dataset_hash
        )
    )
    if existing:
        if existing.report_hash != digest(report):
            raise ValueError("Evidence changed; record a new reference dataset revision")
        return existing
    row = PilotProof(
        kind=kind,
        configuration_hash=key,
        behavior_version=BEHAVIOR_VERSION,
        dataset_hash=dataset_hash,
        report_hash=digest(report),
        report=report,
        dependencies=dependencies,
    )
    db.add(row)
    db.flush()
    return row


def approve_proof(db, proof_id, expected_hash, actor, permission_reference, joint_review_confirmed):
    member = db.get(AppUser, actor)
    row = db.scalar(select(PilotProof).where(PilotProof.id == proof_id).with_for_update())
    if not member or member.disabled or member.role != "admin":
        raise ValueError("An active application admin must attest to the reference review")
    if (
        not row
        or row.state != "pending"
        or row.report_hash != expected_hash
        or digest(row.report) != expected_hash
        or row.report.get("dataset_kind") != "permitted_real"
        or not row.report.get("dataset_ready")
        or not evidence_current(db, row.dependencies)
        or row.behavior_version != BEHAVIOR_VERSION
    ):
        raise ValueError("Proof is missing, changed, expired, synthetic or fails the release gate")
    if not joint_review_confirmed or not permission_reference or len(permission_reference) > 160:
        raise ValueError("Confirm joint reference review and a bounded private permission-record identifier")
    if row.kind == "recognition" and not any(c["supported"] for c in row.report["categories"].values()):
        raise ValueError("No recognition category meets its held-out gate")
    row.state, row.actor = "approved", actor
    row.attestation = {"permission_reference": permission_reference, "joint_review": True, "at": utcnow().isoformat()}
    if row.kind == "recognition":
        for flower, result in row.report["categories"].items():
            support = db.scalar(
                select(RecognitionSupport).where(
                    RecognitionSupport.configuration_hash == row.configuration_hash,
                    RecognitionSupport.taxonomy_version == row.report.get("taxonomy_version", "flowers-v2"),
                    RecognitionSupport.flower == flower,
                )
            )
            if not support:
                support = RecognitionSupport(
                    configuration_hash=row.configuration_hash,
                    taxonomy_version=row.report.get("taxonomy_version", "flowers-v2"),
                    flower=flower,
                )
                db.add(support)
            support.state = "supported" if result["supported"] else "tentative"
            support.report = {"proof_id": row.id, "report_hash": row.report_hash, "metrics": result}
    return row


def readiness(db, configuration=None):
    if configuration is None:
        from .discovery import settings_row

        configuration = settings_row(db).configuration
    key = configuration_hash(offer_configuration(configuration))
    proofs = list(
        db.scalars(
            select(PilotProof).where(
                PilotProof.configuration_hash == key,
                PilotProof.behavior_version == BEHAVIOR_VERSION,
                PilotProof.state == "approved",
            )
        )
    )
    valid = [
        p
        for p in proofs
        if digest(p.report) == p.report_hash
        and p.report.get("dataset_ready")
        and p.report.get("dataset_kind") == "permitted_real"
        and p.attestation.get("joint_review")
        and evidence_current(db, p.dependencies)
    ]
    ready = {kind: any(p.kind == kind for p in valid) for kind in ["conversation", "recognition"]}
    return {
        "configuration_hash": key,
        "behavior_version": BEHAVIOR_VERSION,
        "conversation_proof": ready["conversation"],
        "recognition_proof": ready["recognition"],
        "ready": all(ready.values()),
        "proof_ids": [p.id for p in valid],
        "live_results": "Installed audited proofs" if all(ready.values()) else "Not yet validated on real data",
    }
