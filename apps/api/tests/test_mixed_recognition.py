import hashlib
import io
from datetime import timedelta
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select

from bouquetbrowse.conversation_models import TaxonomyTerm
from bouquetbrowse.db import utcnow
from bouquetbrowse.models import MediaAsset
from bouquetbrowse.offer_contracts import OfferInterpretation
from bouquetbrowse.offers import component_count
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.recognition import (
    analyze_offer,
    configuration_hash,
    crop_image,
    merge_components,
    proposed_regions,
    recheck_offer,
)
from bouquetbrowse.recognition_contracts import FlowerVisual, RecognitionResult, RegionBounds, RegionProposal
from bouquetbrowse.recognition_evaluation import evaluate_images
from bouquetbrowse.recognition_models import ImageRegion, RecognitionSupport

CONFIG = {
    "extraction_model": "gpt-6-luna",
    "escalation_model": "gpt-6.1-sol",
    "taxonomy_version": "flowers-v2",
    "recognition_version": "mixed-flowers-v1",
}


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (800, 600), "pink").save(output, format="JPEG")
    return output.getvalue()


def result(flowers=None, regions=None, interpretation=True):
    return RecognitionResult(
        interpretation=OfferInterpretation(seller_offer=False, ownership=None, location=None, multi_product=False)
        if interpretation
        else None,
        flowers=flowers or [],
        regions=regions or [],
        arrangement="bouquet",
        colors=["pink"],
        multi_product=False,
    )


def bundle_with_media(db, count, monkeypatch):
    content = image_bytes()
    media = []
    for index in range(count):
        asset = MediaAsset(
            state="ready",
            storage_key=f"fictional-{index}.jpg",
            checksum=hashlib.sha256(content + str(index).encode()).hexdigest(),
            retention_until=utcnow() + timedelta(days=90),
        )
        db.add(asset)
        db.flush()
        media.append(
            {"media_id": asset.id, "version_id": f"fictional-version-{index}", "role": "seller_image", "region": None}
        )
    db.commit()
    monkeypatch.setattr("bouquetbrowse.storage.get_media_bytes", lambda key: content)
    return {"messages": [], "media": media}


def test_component_counts_do_not_become_bouquet_totals():
    assert component_count("20 roses and 5 peonies", "rose") == 20
    assert component_count("20 roses and 5 peonies", "peony") == 5
    assert component_count("15 bông hồng", "rose") == 15
    assert component_count("20 roses or 25 roses", "rose") is None


def test_regions_are_finite_ordered_and_bounded():
    for bounds in [(0.8, 0, 0.2, 1), (-0.1, 0, 1, 1), (0, 0, float("nan"), 1), (0, 0, 0.001, 0.001)]:
        with pytest.raises(ValidationError):
            RegionBounds(left=bounds[0], top=bounds[1], right=bounds[2], bottom=bounds[3])
    content = crop_image(image_bytes(), RegionBounds(left=0.25, top=0.25, right=0.75, bottom=0.75))
    with Image.open(io.BytesIO(content)) as cropped:
        assert cropped.size == (400, 300)


def test_joint_processing_chunks_and_records_unprocessed_media(db, monkeypatch):
    bundle = bundle_with_media(db, 10, monkeypatch)
    calls = []

    def fake(context, views, configuration, **kwargs):
        calls.append([v["view_id"] for v in views])
        return result([FlowerVisual(flower="rose", state="present", view_ids=[views[0]["view_id"]])])

    output = analyze_offer(bundle, CONFIG, call=fake)
    assert [len(call) for call in calls] == [4, 4]
    assert len(output["unprocessed_media"]) == 2


def test_missing_media_never_counts_as_completed_recognition(db, monkeypatch):
    bundle = bundle_with_media(db, 1, monkeypatch)
    asset = db.get(MediaAsset, bundle["media"][0]["media_id"])
    asset.state = "pending"
    db.commit()
    with pytest.raises(CapabilityError, match="not ready"):
        analyze_offer(bundle, CONFIG, call=lambda *a: pytest.fail("Model must not run"))


def test_visual_labels_stay_tentative_without_matching_benchmark(db):
    views = [{"view_id": "view", "media_id": "media", "checksum": "a" * 64}]
    outputs = [
        result([FlowerVisual(flower=flower, state="present", view_ids=["view"]) for flower in ["rose", "peony"]])
    ]
    components = merge_components(db, [], outputs, CONFIG, views)
    assert {c["flower"] for c in components} == {"rose", "peony"}
    assert all(not c["supported"] and c["visual_state"] == "tentative" for c in components)
    db.add(
        RecognitionSupport(
            configuration_hash=configuration_hash(CONFIG),
            taxonomy_version="flowers-v2",
            flower="rose",
            state="supported",
            report={"synthetic_test_only": True},
        )
    )
    db.flush()
    components = merge_components(db, [], outputs, CONFIG, views)
    assert not next(c for c in components if c["flower"] == "rose")[
        "supported"
    ]  # Unbacked flags cannot certify labels.
    changed = {**CONFIG, "extraction_model": "gpt-6.1-sol"}
    assert not any(c["supported"] for c in merge_components(db, [], outputs, changed, views))


def test_ambiguous_alternatives_do_not_become_confirmed_tags(db):
    views = [{"view_id": "view", "media_id": "media", "checksum": "a" * 64}]
    observed = FlowerVisual(flower="peony", state="alternative", view_ids=["view"], alternatives=["lisianthus"])
    components = merge_components(db, [], [result([observed])], CONFIG, views)
    assert len(components) == 1 and components[0]["alternatives"] == ["lisianthus"]
    assert not components[0]["supported"]
    assert components[0]["stated_count"] is None


def test_new_taxonomy_labels_need_review(db):
    outputs = [result([FlowerVisual(flower="unvalidated-cultivar", state="present", view_ids=["view"])])]
    assert merge_components(db, [], outputs, CONFIG, []) == []
    assert db.scalar(select(TaxonomyTerm)).state == "proposed"


def test_targeted_analysis_regions_preserve_image_identity(db, monkeypatch):
    from bouquetbrowse.recognition import prepare_views

    bundle = bundle_with_media(db, 1, monkeypatch)
    views = prepare_views(bundle)
    proposal = RegionProposal(
        media_id=views[0]["media_id"], bounds=RegionBounds(left=0, top=0, right=0.5, bottom=0.5), reason="small_fillers"
    )
    ids = proposed_regions(db, SimpleNamespace(id="synthetic-analysis"), [result(regions=[proposal])], views)
    db.commit()
    calls = []

    def fake(context, selected, configuration, **kwargs):
        calls.append(kwargs)
        assert selected[0]["view_id"] == ids[0]
        return result(interpretation=False)

    recheck_offer(bundle, CONFIG, ids, call=fake)
    assert calls == [{"purpose": "regional_recheck", "stronger": True}]
    region = db.get(ImageRegion, ids[0])
    region.checksum = "b" * 64
    db.commit()
    with pytest.raises(CapabilityError, match="changed"):
        recheck_offer(bundle, CONFIG, ids, call=fake)


def test_product_regions_do_not_automatically_split_offers(db, monkeypatch):
    from bouquetbrowse.recognition import prepare_views

    bundle = bundle_with_media(db, 1, monkeypatch)
    views = prepare_views(bundle)
    proposal = RegionProposal(
        media_id=views[0]["media_id"], bounds=RegionBounds(left=0, top=0, right=0.5, bottom=1), reason="multi_product"
    )
    ids = proposed_regions(db, SimpleNamespace(id="synthetic-analysis"), [result(regions=[proposal])], views)
    db.commit()
    assert db.get(ImageRegion, ids[0]).state == "proposed"
    assert recheck_offer(bundle, CONFIG, ids, call=lambda *a, **k: pytest.fail("Product regions need review")) == (
        None,
        [],
    )


def judgments(count=100):
    return [
        {
            "image_id": f"fictional-{i}",
            "checksum": hashlib.sha256(str(i).encode()).hexdigest(),
            "seller_group": "fictional-dev" if i < 60 else "fictional-holdout",
            "image_family": f"family-{i}",
            "split": "development" if i < 60 else "holdout",
            "labels": ["rose"] if i % 2 == 0 else [],
            "assessable": ["rose"],
            "joint_predictions": ["rose"] if i % 2 == 0 else [],
            "image_only_predictions": [],
            "reviewers": ["fictional-a", "fictional-b"] if i < 20 else ["fictional-a"],
            "latency_ms": 100,
            "cost_microusd": 1000,
        }
        for i in range(count)
    ]


def test_benchmark_reports_counts_intervals_and_cannot_certify_synthetic_data():
    report = evaluate_images(judgments(), "fictional-config")
    assert not report["dataset_ready"] and not report["categories"]["rose"]["supported"]
    permitted = evaluate_images(judgments(), "fictional-config", "permitted_real")
    rose = permitted["categories"]["rose"]
    assert rose["supported"] and rose["joint_holdout"]["tp"] == 20
    assert rose["joint_holdout"]["precision_interval"][0] < 1
    assert rose["image_only_holdout"]["recall"] == 0
    assert not permitted["categories"]["peony"]["supported"]


def test_benchmark_rejects_leakage_and_duplicate_images():
    rows = judgments()
    rows[-1]["seller_group"] = rows[0]["seller_group"]
    with pytest.raises(ValueError, match="leakage"):
        evaluate_images(rows, "config")
    rows = judgments()
    rows[-1]["checksum"] = rows[0]["checksum"]
    with pytest.raises(ValueError, match="distinct"):
        evaluate_images(rows, "config")


def test_image_only_path_omits_conversation_and_reuses_receipt(db, monkeypatch):
    import openai

    from bouquetbrowse import recognition
    from bouquetbrowse.config import Settings
    from bouquetbrowse.recognition_models import RecognitionRecord

    monkeypatch.setattr(
        recognition, "get_settings", lambda: Settings(openai_api_key="fictional-test-key", _env_file=None)
    )
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        assert "PRIVATE_BUYER_TEXT" not in str(kwargs)
        return SimpleNamespace(
            output_parsed=result(interpretation=False),
            usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 10, "output_tokens": 10}),
        )

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    views = [
        {
            "view_id": "synthetic-view",
            "media_id": "synthetic-media",
            "checksum": "a" * 64,
            "content_hash": "b" * 64,
            "bytes": image_bytes(),
        }
    ]
    bundle = {"messages": ["PRIVATE_BUYER_TEXT"], "media": []}
    recognition.recognize_call(bundle, views, CONFIG, purpose="image_only")
    recognition.recognize_call(bundle, views, CONFIG, purpose="image_only")
    assert len(calls) == 1
    db.expire_all()
    record = db.scalar(select(RecognitionRecord))
    assert record.purpose == "image_only" and record.offer_id is None
    assert record.result["interpretation"] is None
