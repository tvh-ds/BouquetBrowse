"""Private, bounded evaluation commands. No result can publish a catalog revision."""

import hashlib
import json
import time
from datetime import timedelta

from sqlalchemy import select

from . import db as database
from .config import ROOT
from .conversation_models import OfferOccurrence
from .db import aware, utcnow
from .executions import create_execution, pinned_execution
from .leases import guard
from .model_calls import CallScope, call_scope
from .models import CostEntry, MediaAsset
from .offers import evidence_bundle
from .pipeline import digest
from .providers import CapabilityError
from .recognition import analyze_offer, configuration_hash, crop_image, prepare_views, recognize_call, request_identity
from .recognition_contracts import RecognitionResult
from .recognition_models import RecognitionRecord
from .research_models import EvaluationDataset, EvaluationItem
from .runtime_models import ModelCall


def checked_item(db, item):
    dataset = db.get(EvaluationDataset, item.dataset_id) if item else None
    offer = db.get(OfferOccurrence, item.offer_id) if item else None
    asset = db.get(MediaAsset, item.media_id) if item else None
    if (
        not item
        or not dataset
        or aware(dataset.retention_until) <= utcnow()
        or aware(item.retention_until) <= utcnow()
        or not offer
        or offer.input_fingerprint != item.offer_fingerprint
        or offer.state in {"withdrawn", "expired", "rejected", "split"}
        or not asset
        or asset.state != "ready"
        or asset.checksum != item.checksum
    ):
        raise CapabilityError("Evaluation source evidence changed or expired.", "evaluation_stale")
    bundle = evidence_bundle(db, offer)
    bundle["media"] = [m for m in bundle["media"] if m["media_id"] == item.media_id]
    if len(bundle["media"]) != 1:
        raise ValueError("Evaluation needs one uniquely associated source image")
    return dataset, bundle


def queue_dataset(db, dataset):
    from .config import get_settings

    if not get_settings().openai_api_key:
        raise CapabilityError("Set the local model key before explicitly running evaluation.", "model_not_configured")
    items = list(db.scalars(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset.id)))
    groups = {}
    for item in items:
        checked_item(db, item)
        if item.labels is None or not item.reviewers:
            raise ValueError("Annotate each image before running models; predictions stay hidden until annotation")
        for key in [("seller", item.seller_group), ("family", item.image_family)]:
            groups.setdefault(key, set()).add(item.split)
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError("Seller/image-family leakage between development and holdout")
    ids = []
    for item in items:
        if item.state == "completed":
            continue
        if item.execution_id:
            from .runtime_models import GraphExecution

            previous = db.get(GraphExecution, item.execution_id)
            if previous and previous.state in {"paused", "failed", "withdrawn", "cancelled", "superseded"}:
                raise CapabilityError(
                    "Inspect/retry the existing evaluation job; uncertain calls need explicit replay.",
                    "evaluation_retry_required",
                )
            if previous:
                ids.append(previous.id)
                continue
        execution = create_execution(
            db,
            "evaluation",
            f"{dataset.id}:{item.id}",
            dataset.configuration,
            digest([item.offer_fingerprint, item.checksum]),
            item.offer_id,
        )
        execution.progress = {**execution.progress, "evaluation_item_id": item.id}
        item.execution_id, item.state = execution.id, "queued"
        ids.append(execution.id)
    return ids


def predictions(db, record, media_id, taxonomy_version):
    from .taxonomy import normalize

    views = {v["view_id"] for v in record.dependencies.get("views", []) if v["media_id"] == media_id}
    return sorted(
        {
            name
            for name in {
                normalize(db, f["flower"], taxonomy_version)
                for f in record.result.get("flowers", [])
                if f.get("state") == "present" and not f.get("alternatives") and set(f.get("view_ids", [])) & views
            }
            if name is not None
        }
    )


def judgments(db, dataset):
    values = []
    for item in db.scalars(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset.id)):
        checked_item(db, item)
        joint, image = (
            db.get(RecognitionRecord, item.joint_record_id),
            db.get(RecognitionRecord, item.image_only_record_id),
        )
        if (
            item.state != "completed"
            or not joint
            or not image
            or not joint.result
            or not image.result
            or item.labels is None
        ):
            raise ValueError("Every evaluation item needs current annotations and completed joint/image-only receipts")
        values.append(
            {
                "image_id": item.media_id,
                "checksum": item.checksum,
                "seller_group": item.seller_group,
                "image_family": item.image_family,
                "split": item.split,
                "labels": item.labels,
                "assessable": item.assessable,
                "reviewers": item.reviewers,
                "joint_predictions": predictions(db, joint, item.media_id, dataset.configuration["taxonomy_version"]),
                "image_only_predictions": predictions(
                    db, image, item.media_id, dataset.configuration["taxonomy_version"]
                ),
                "joint_record_id": joint.id,
                "image_only_record_id": image.id,
                "latency_ms": item.latency_ms,
                "cost_microusd": item.cost_microusd,
            }
        )
    return values


def export_dataset(db, dataset):
    folder = ROOT / ".data" / "evaluations"
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / ".bouquetbrowse-evaluations"
    if not marker.exists():
        if any(folder.iterdir()):
            raise ValueError("Evaluation export directory lacks ownership evidence")
        marker.write_text("BouquetBrowse evaluation exports v1", encoding="utf-8")
    if marker.read_text(encoding="utf-8") != "BouquetBrowse evaluation exports v1":
        raise ValueError("Invalid evaluation export ownership marker")
    values = judgments(db, dataset)
    name = f"{dataset.id}-{dataset.version}-{digest(values)[:12]}.jsonl"
    target = folder / name
    if target.exists():
        raise ValueError("This immutable evaluation export already exists")
    with target.open("x", encoding="utf-8") as stream:
        stream.write("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values))
    dataset.export_keys = sorted(set([*dataset.export_keys, name]))
    return target


def expire_research(db, now=None, media_ids=None, offer_ids=None):
    from .leases import cancel
    from .pilot_models import PilotProof
    from .pipeline import enqueue
    from .runtime_models import GraphExecution

    now, media_ids, offer_ids = now or utcnow(), set(media_ids or []), set(offer_ids or [])
    for item in db.scalars(select(EvaluationItem)):
        if item.media_id in media_ids or item.offer_id in offer_ids or aware(item.retention_until) <= now:
            item.labels, item.assessable, item.reviewers, item.history, item.state = None, [], [], [], "expired"
            item.retention_until = now
            dataset = db.get(EvaluationDataset, item.dataset_id)
            dataset.retention_until = now
    for dataset in db.scalars(select(EvaluationDataset).where(EvaluationDataset.retention_until <= now)):
        if dataset.export_keys:
            enqueue(
                db, "delete-evaluation-exports", {"dataset_id": dataset.id}, f"delete-evaluation-exports:{dataset.id}"
            )
        dataset.name = "Expired evaluation"
        dataset.actor = "removed"
        if dataset.proof_id:
            db.get(PilotProof, dataset.proof_id).state = "revoked"
        for item in db.scalars(select(EvaluationItem).where(EvaluationItem.dataset_id == dataset.id)):
            item.labels, item.assessable, item.reviewers, item.history, item.state = None, [], [], [], "expired"
            item.seller_group, item.image_family = "expired", "expired"
            if item.execution_id:
                execution = db.get(GraphExecution, item.execution_id)
                cancel(db, execution.job_id)
                execution.state = "withdrawn"
                enqueue(db, "delete-checkpoints", {"execution_id": execution.id}, f"delete-checkpoints:{execution.id}")
                for call in db.scalars(select(ModelCall).where(ModelCall.execution_id == execution.id)):
                    call.result, call.usage, call.state, call.replay_authorized = None, {}, "removed", False


def delete_exports(dataset_id, factory):
    folder = (ROOT / ".data" / "evaluations").resolve()
    marker = folder / ".bouquetbrowse-evaluations"
    with factory() as db:
        dataset = db.get(EvaluationDataset, dataset_id)
        if not dataset or aware(dataset.retention_until) > utcnow():
            return {"deleted": 0}
        names = list(dataset.export_keys)
    owned = marker.is_file() and marker.read_text(encoding="utf-8") == "BouquetBrowse evaluation exports v1"
    count = 0
    for name in names:
        candidate = folder / name
        target = candidate.resolve()
        if (
            not owned
            or candidate.is_symlink()
            or target.parent != folder
            or not name.startswith(dataset_id + "-")
            or not name.endswith(".jsonl")
        ):
            raise ValueError("Refusing an unowned evaluation export deletion")
        if target.is_file():
            target.unlink()
            count += 1
    return {"deleted": count}


class EvaluationServices:
    def __init__(self, execution_id, lease, call=recognize_call):
        self.execution_id, self.lease, self.call = execution_id, lease, call

    def checked(self, db):
        guard(db, self.lease)
        execution = pinned_execution(db, self.execution_id)
        if (
            execution.kind != "evaluation"
            or execution.job_id != self.lease.job_id
            or execution.state in {"cancelled", "withdrawn", "superseded"}
        ):
            raise CapabilityError("Evaluation execution is inactive.", "execution_cancelled")
        item = db.get(EvaluationItem, execution.progress.get("evaluation_item_id"))
        dataset, bundle = checked_item(db, item)
        return execution, item, dataset, bundle

    def stage(self, name, state):
        with database.SessionLocal() as db:
            execution, item, dataset, bundle = self.checked(db)
            if name == "finish":
                item.state, execution.state = "completed", "completed"
                db.commit()
                return {}
            if getattr(item, f"{name}_record_id"):
                record = db.get(RecognitionRecord, getattr(item, f"{name}_record_id"))
                if not record or not record.result or aware(record.retention_until) <= utcnow():
                    raise CapabilityError(
                        "Evaluation receipt expired; create a new explicit evaluation.", "call_expired"
                    )
                db.commit()
                return {}
            configuration = dict(execution.configuration)
            scope = CallScope(execution.id, execution.budget_microusd, execution.id, self.lease)
            item.state, execution.state = "processing", "processing"
            db.commit()
        started = time.monotonic()
        with call_scope(scope):
            if name == "joint":
                output = analyze_offer(bundle, configuration, call=self.call)
                views, results = output["views"], output["results"]
                children = [self.record(bundle, views, configuration, "joint")]
                # The same regional proposals and bounded stronger call used by production.
                crops = []
                for result in results:
                    for region in result.regions:
                        if region.reason == "multi_product" or len(crops) >= 4:
                            continue
                        source = next(v for v in views if v["media_id"] == region.media_id)
                        content = crop_image(source["bytes"], region.bounds)
                        crops.append(
                            {
                                **source,
                                "view_id": digest([source["view_id"], region.bounds.coordinates()])[:36],
                                "bytes": content,
                                "content_hash": hashlib.sha256(content).hexdigest(),
                            }
                        )
                if crops:
                    results.append(self.call(bundle, crops, configuration, purpose="regional_recheck", stronger=True))
                    children.append(self.record(bundle, crops, configuration, "regional_recheck", True))
                record_id = self.composite(results, [*views, *crops], children, configuration)
            else:
                views = prepare_views(bundle)
                self.call(bundle, views, configuration, purpose="image_only")
                record_id = self.record(bundle, views, configuration, "image_only")
        elapsed = round((time.monotonic() - started) * 1000)
        with database.SessionLocal() as db:
            execution, item, _, _ = self.checked(db)
            setattr(item, f"{name}_record_id", record_id)
            item.latency_ms += elapsed
            item.cost_microusd = sum(
                db.scalars(
                    select(CostEntry.amount_microusd)
                    .join(ModelCall, ModelCall.cost_id == CostEntry.id)
                    .where(ModelCall.execution_id == execution.id, ModelCall.state == "succeeded")
                )
            )
            db.commit()
        return {}

    def record(self, bundle, views, configuration, purpose, stronger=False):
        _, _, dependencies = request_identity(bundle, views, configuration, purpose, stronger)
        with database.SessionLocal() as db:
            record = db.scalar(select(RecognitionRecord).where(RecognitionRecord.cache_key == digest(dependencies)))
            if not record or not record.result or aware(record.retention_until) <= utcnow():
                raise ValueError("Evaluation needs a durable recognition receipt")
            return record.id

    def composite(self, results, views, children, configuration):
        ambiguous = {
            name for result in results for f in result.flowers if f.alternatives for name in [f.flower, *f.alternatives]
        }
        flowers = [
            f.model_copy(update={"state": "tentative"}) if f.flower in ambiguous else f
            for r in results
            for f in r.flowers
        ]
        result = RecognitionResult.model_validate(
            {
                **results[0].model_dump(),
                "flowers": flowers[:24],
                "warnings": [
                    *results[0].warnings,
                    *(["Evaluation composition truncated at 24 observations"] if len(flowers) > 24 else []),
                ][:10],
            }
        )
        key = digest({"evaluation_joint": children, "configuration": configuration_hash(configuration)})
        with database.SessionLocal() as db:
            execution, _, _, _ = self.checked(db)
            row = db.scalar(select(RecognitionRecord).where(RecognitionRecord.cache_key == key))
            if not row:
                row = RecognitionRecord(
                    cache_key=key,
                    purpose="joint",
                    offer_id=execution.offer_id,
                    configuration_hash=configuration_hash(configuration),
                    result=result.model_dump(mode="json"),
                    dependencies={
                        "derived_from": children,
                        "views": [
                            {k: v[k] for k in ["view_id", "media_id", "checksum", "content_hash"]} for v in views
                        ],
                    },
                    retention_until=utcnow() + timedelta(days=30),
                )
                db.add(row)
                db.flush()
            db.commit()
            return row.id


def run_evaluation(execution_id, lease):
    from .config import get_settings
    from .graphs import evaluation_graph, invoke_graph, postgres_checkpointer

    with postgres_checkpointer(get_settings().database_url) as saver:
        invoke_graph(evaluation_graph(EvaluationServices(execution_id, lease), saver), execution_id)
    return {"execution_id": execution_id, "evaluation_only": True}
