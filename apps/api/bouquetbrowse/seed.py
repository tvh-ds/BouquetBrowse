"""Public-repository-safe fictional records. No live seller identities or quotations."""

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .catalog import demo_vector
from .db import utcnow
from .extraction import extract_caption
from .models import (
    AvailabilityObservation,
    ExtractionRun,
    FieldAssertion,
    ImageEmbedding,
    Listing,
    ListingRevision,
    ListingSource,
    MediaAsset,
    ModelVersion,
    PostMedia,
    PostVersion,
    PriceObservation,
    ReviewAction,
    Seller,
    SourceAccount,
    SourcePost,
    TextEmbedding,
)
from .pipeline import digest


def stable(value):
    return str(uuid5(NAMESPACE_URL, "bouquetbrowse-demo:" + value))


SELLERS = [
    ("Mây Flower Studio", "Ba Đình"),
    ("Thơm Atelier", "Tây Hồ"),
    ("Nắng Floral", "Hoàn Kiếm"),
    ("Lá & Hoa", "Cầu Giấy"),
    ("Bông Nhỏ", "Đống Đa"),
    ("An Nhiên Flowers", "Hai Bà Trưng"),
    ("The Petal Room", "Thanh Xuân"),
    ("Mùa Flowers", "Nam Từ Liêm"),
]
VARIANTS = [
    {
        "name": "Hồng dịu dàng",
        "en": "Softly, in pink",
        "flower": "rose",
        "color": "pink",
        "count": 20,
        "image": "pink",
        "occasion": "anniversary",
        "style": "romantic",
        "base": 650000,
        "caption": "Bó hoa hồng màu hồng, 20 cành. Giấy gói thanh lịch, phong cách lãng mạn, kỷ niệm.",
    },
    {
        "name": "Một ngày trong veo",
        "en": "A little white poetry",
        "flower": "rose",
        "color": "white",
        "count": 15,
        "image": "white",
        "occasion": "birthday",
        "style": "natural",
        "base": 590000,
        "caption": "Bó hoa hồng trắng, 15 cành. Giấy kraft, phong cách tự nhiên, sinh nhật.",
    },
    {
        "name": "Gửi một chút nắng",
        "en": "A little pocket of sunshine",
        "flower": "sunflower",
        "color": "yellow",
        "count": 10,
        "image": "golden",
        "occasion": "graduation",
        "style": "natural",
        "base": 450000,
        "caption": "Bó hướng dương vàng, 10 cành. Giấy gói, tự nhiên, tốt nghiệp.",
    },
]


def seed_demo(db):
    if db.scalar(select(Listing.id).where(Listing.is_demo.is_(True)).limit(1)):
        return {"seeded": False}
    models = [
        ModelVersion(
            name="demo-lexical-v1", revision="fictional-fixtures-v1", dimensions=1536, configuration={"synthetic": True}
        ),
        ModelVersion(
            name="demo-visual-v1",
            revision="fictional-fixtures-v1",
            dimensions=768,
            configuration={"synthetic": True, "not_model_inference": True},
        ),
    ]
    db.add_all(models)
    assets = {}
    for image, concept in [
        ("pink", "rose pink romantic"),
        ("white", "rose white natural"),
        ("golden", "sunflower yellow natural"),
    ]:
        asset = MediaAsset(
            id=stable(f"media-{image}"),
            state="demo",
            mime="image/png",
            width=1024,
            height=1365,
            rights={
                "generated": True,
                "fixture_path": f"/images/demo-{image}.png",
                "provenance": f"/images/demo-{image}.json",
            },
        )
        db.add(asset)
        db.flush()
        assets[image] = asset
        db.add(ImageEmbedding(media_id=asset.id, model_version="demo-visual-v1", vector=demo_vector(concept)[:768]))
    for seller_index, (name, district) in enumerate(SELLERS):
        seller = Seller(
            id=stable(f"seller-{seller_index}"),
            name=name,
            slug=f"demo-florist-{seller_index + 1}",
            district=district,
            bio="Studio hư cấu được tạo riêng cho bản thử nghiệm BouquetBrowse. Không phải người bán thật.",
            is_demo=True,
        )
        db.add(seller)
        db.flush()
        platform = "instagram" if seller_index % 2 == 0 else "threads"
        account = SourceAccount(
            id=stable(f"account-{seller_index}"),
            seller_id=seller.id,
            platform=platform,
            username=f"demo.florist.{seller_index + 1}",
            capabilities={"demo": True},
        )
        db.add(account)
        db.flush()
        specs = [dict(v) for v in VARIANTS]
        if seller_index < 6:
            extra = dict(VARIANTS[0 if seller_index % 2 == 0 else 1])
            extra.update(
                name=[
                    "Hồng nhỏ xinh",
                    "Trắng tinh khôi",
                    "Một khoảng hồng",
                    "Nhẹ như mây",
                    "Hồng theo ý bạn",
                    "Món quà chưa định giá",
                ][seller_index],
                en=[
                    "A smaller pink gesture",
                    "Simply white",
                    "Pink, remembered",
                    "Light as a cloud",
                    "Pink, your way",
                    "A gift to ask about",
                ][seller_index],
            )
            if seller_index == 0:
                extra.update(count=12, base=390000, caption="Bó hoa hồng màu hồng, 12 cành. Giấy gói lãng mạn.")
            if seller_index == 1:
                extra["kind"] = "range"
            if seller_index == 2:
                extra["stale"] = True
            if seller_index == 3:
                extra.update(count=None, caption="Bó hoa hồng trắng cỡ vừa, giấy kraft.")
            if seller_index == 4:
                extra["kind"] = "from"
            if seller_index == 5:
                extra["kind"] = "unknown"
            specs.append(extra)
        for variant_index, spec in enumerate(specs):
            listing_id = stable(f"listing-{seller_index}-{variant_index}")
            price = spec["base"] + [-50000, -30000, 10000, 0, 40000, 60000, 90000, 120000][seller_index]
            listing = Listing(
                id=listing_id,
                seller_id=seller.id,
                configuration_key=digest(["demo", seller_index, variant_index]),
                title=spec["name"],
                description=f"{spec['caption']} Mẫu minh họa; xác nhận chi tiết trực tiếp với người bán khi dùng dữ liệu thật.",
                primary_flower=spec["flower"],
                color=spec["color"],
                arrangement="bouquet",
                stem_count=spec["count"],
                image_path=f"/images/demo-{spec['image']}.png",
                style=spec["style"],
                occasion=spec["occasion"],
                attributes={
                    "title_en": spec["en"],
                    "size_reviewed": spec["count"] is not None,
                    "extraction_reviewed": True,
                    "wrapping": "paper",
                    "warnings": ["Fictional demonstration record"],
                },
                state="published",
                is_demo=True,
                search_text=" ".join(
                    [
                        spec["name"],
                        spec["en"],
                        spec["caption"],
                        spec["flower"],
                        spec["color"],
                        spec["style"],
                        spec["occasion"],
                        "bouquet",
                    ]
                ),
            )
            db.add(listing)
            db.flush()
            latest_version = None
            for age, adjustment in [(28, -40000), (14, -20000), (3 + seller_index % 4, 0)]:
                days = age + 35 if spec.get("stale") else age
                published = utcnow() - timedelta(days=days)
                post = SourcePost(
                    id=stable(f"post-{seller_index}-{variant_index}-{age}"),
                    account_id=account.id,
                    platform=platform,
                    platform_post_id=f"demo-{seller_index}-{variant_index}-{age}",
                    url=None,
                    published_at=published,
                    last_seen_at=utcnow(),
                    is_demo=True,
                )
                db.add(post)
                db.flush()
                kind = spec.get("kind", "exact")
                current_amount = price + adjustment
                price_text = (
                    "Liên hệ để hỏi giá."
                    if kind == "unknown"
                    else f"Giá từ {current_amount // 1000}k."
                    if kind == "from"
                    else f"Giá {current_amount // 1000}k–{current_amount // 1000 + 150}k."
                    if kind == "range"
                    else f"Giá {current_amount // 1000}k."
                )
                caption = f"{spec['caption']} {price_text} Đặt trước 2 ngày. Có giao hàng. Phí ship 30k."
                version = PostVersion(
                    id=stable(f"version-{seller_index}-{variant_index}-{age}"),
                    post_id=post.id,
                    caption=caption,
                    payload={"synthetic": True, "fixture_version": "v1"},
                    content_hash=digest([listing.id, age, caption]),
                    retention_until=utcnow() + timedelta(days=30),
                )
                db.add(version)
                db.flush()
                latest_version = version
                db.add(ListingSource(listing_id=listing.id, version_id=version.id))
                db.add(PostMedia(version_id=version.id, media_id=assets[spec["image"]].id, position=0))
                if kind != "unknown":
                    db.add(
                        PriceObservation(
                            listing_id=listing.id,
                            version_id=version.id,
                            amount_min=current_amount,
                            amount_max=current_amount + 150000 if kind == "range" else current_amount,
                            currency="VND",
                            kind=kind,
                            component="bouquet",
                            evidence={"quote": price_text, "fictional": True, "currency_basis": "seller_market"},
                            reviewed=True,
                            advertised_at=published,
                            superseded=adjustment != 0,
                        )
                    )
            result = extract_caption(latest_version.caption)
            run = ExtractionRun(
                version_id=latest_version.id,
                input_hash=digest([listing.id, "fixture"]),
                pipeline_version="demo-v1",
                provider="fixture",
                output=result.model_dump(mode="json"),
            )
            db.add(run)
            db.flush()
            for field in ["arrangement", "primary_flower", "color", "stem_count", "lead_days", "delivery", "wrapping"]:
                claim = getattr(result, field)
                db.add(
                    FieldAssertion(
                        listing_id=listing.id,
                        run_id=run.id,
                        field=field,
                        value={"value": claim.value},
                        evidence=[{**e.model_dump(), "version_id": latest_version.id} for e in claim.evidence_refs],
                        status=claim.status,
                        review_state="accepted",
                    )
                )
            db.add(
                AvailabilityObservation(
                    listing_id=listing.id,
                    version_id=latest_version.id,
                    status="preorder",
                    lead_days=2,
                    delivery=True,
                    evidence={"fictional": True, "quote": "Đặt trước 2 ngày. Có giao hàng."},
                )
            )
            revision = ListingRevision(
                listing_id=listing.id,
                snapshot={"title": listing.title, "stem_count": listing.stem_count, "fictional": True},
                pipeline_version="demo-v1",
            )
            db.add(revision)
            db.flush()
            listing.current_revision_id = revision.id
            db.add(
                TextEmbedding(
                    revision_id=revision.id, model_version="demo-lexical-v1", vector=demo_vector(listing.search_text)
                )
            )
            db.add(
                ReviewAction(
                    listing_id=listing.id,
                    actor="demo-fixture",
                    decision="accept",
                    reason="Synthetic fixture; not a human review of real seller content.",
                    changes={"fixture": True},
                )
            )
    db.commit()
    return {"seeded": True, "listings": 30, "sellers": 8}
