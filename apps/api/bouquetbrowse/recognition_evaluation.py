"""Offline, deterministic evaluation. Reading labels never runs models or publishes offers."""

import math
from collections import defaultdict

from pydantic import Field, model_validator

from .extraction import FLOWERS
from .schemas import StrictModel


class ImageJudgment(StrictModel):
    image_id: str = Field(min_length=1, max_length=160)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    seller_group: str = Field(min_length=1, max_length=160)
    image_family: str = Field(min_length=1, max_length=160)
    split: str = Field(pattern=r"^(development|holdout)$")
    labels: list[str]
    assessable: list[str]
    joint_predictions: list[str]
    image_only_predictions: list[str]
    joint_record_id: str | None = None
    image_only_record_id: str | None = None
    reviewers: list[str] = Field(min_length=1, max_length=5)
    latency_ms: int = Field(ge=0)
    cost_microusd: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_labels(self):
        if set(self.labels) - set(self.assessable):
            raise ValueError("Visible labels must be assessable")
        import re

        if any(
            not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value)
            for value in [*self.assessable, *self.joint_predictions, *self.image_only_predictions]
        ):
            raise ValueError("Invalid flower category key")
        return self


def wilson(successes, total):
    if not total:
        return None
    z, p = 1.959963984540054, successes / total
    denominator = 1 + z * z / total
    midpoint = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0, midpoint - radius), min(1, midpoint + radius)]


def category_metrics(rows, flower, prediction_field):
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for row in rows:
        if flower not in row.assessable:
            continue
        positive, predicted = flower in row.labels, flower in getattr(row, prediction_field)
        counts["tp" if positive and predicted else "fp" if predicted else "fn" if positive else "tn"] += 1
    tp, fp, fn, tn = [counts[key] for key in ["tp", "fp", "fn", "tn"]]
    return {
        **counts,
        "positive": tp + fn,
        "negative": fp + tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "precision_interval": wilson(tp, tp + fp),
        "recall_interval": wilson(tp, tp + fn),
        "prediction_coverage": (tp + fp) / (tp + fp + fn + tn) if tp + fp + fn + tn else None,
    }


def evaluate_images(values, configuration_hash, dataset_kind="synthetic", categories=None):
    if dataset_kind not in {"synthetic", "permitted_real"}:
        raise ValueError("Record the dataset provenance explicitly")
    rows = [ImageJudgment.model_validate(value) for value in values]
    category_keys = set(categories or FLOWERS)
    if any(
        (set(row.assessable) | set(row.joint_predictions) | set(row.image_only_predictions)) - category_keys
        for row in rows
    ):
        raise ValueError("Evaluate curated flower categories only")
    ids, checksums, groups = set(), set(), defaultdict(set)
    for row in rows:
        if row.image_id in ids or row.checksum in checksums:
            raise ValueError("Benchmark images must be distinct")
        ids.add(row.image_id)
        checksums.add(row.checksum)
        groups[("seller", row.seller_group)].add(row.split)
        groups[("family", row.image_family)].add(row.split)
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("Seller/image-family leakage between development and holdout")
    holdout = [row for row in rows if row.split == "holdout"]
    development = [row for row in rows if row.split == "development"]
    double_reviewed = sum(len(set(row.reviewers)) >= 2 for row in rows)
    dataset_ready = (
        len(rows) >= 100
        and len(development) >= 60
        and len(holdout) >= 40
        and double_reviewed >= math.ceil(0.2 * len(rows))
        and dataset_kind == "permitted_real"
    )
    categories = {}
    for flower in sorted(category_keys):
        overall = category_metrics(rows, flower, "joint_predictions")
        joint = category_metrics(holdout, flower, "joint_predictions")
        image_only = category_metrics(holdout, flower, "image_only_predictions")
        sampled = (
            overall["positive"] >= 20
            and overall["negative"] >= 20
            and joint["positive"] >= 10
            and joint["negative"] >= 10
        )
        passes = (
            sampled
            and joint["precision"] is not None
            and joint["precision"] >= 0.95
            and joint["recall"] is not None
            and joint["recall"] >= 0.80
        )
        categories[flower] = {
            "overall": overall,
            "joint_holdout": joint,
            "image_only_holdout": image_only,
            "sufficiently_sampled": sampled,
            "supported": bool(dataset_ready and passes),
        }
    return {
        "schema_version": "mixed-recognition-evaluation-v1",
        "configuration_hash": configuration_hash,
        "dataset_kind": dataset_kind,
        "images": len(rows),
        "development": len(development),
        "holdout": len(holdout),
        "double_reviewed": double_reviewed,
        "dataset_ready": dataset_ready,
        "categories": categories,
        "cost_microusd": sum(row.cost_microusd for row in rows),
        "mean_latency_ms": sum(row.latency_ms for row in rows) / len(rows) if rows else None,
        "notes": [
            "Observed pilot targets, not a universal accuracy guarantee.",
            "Negative predictions include abstentions; report coverage alongside recall.",
            "Image-only evaluation cannot publish catalog content.",
        ],
    }
