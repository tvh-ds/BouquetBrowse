import base64
import hashlib
import json
import math
import re
from datetime import timedelta
from statistics import median, quantiles

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from .db import aware, utcnow
from .extraction import fold
from .models import (
    AvailabilityObservation,
    CohortMember,
    CohortRun,
    ImageEmbedding,
    Listing,
    ListingSource,
    PostMedia,
    PostVersion,
    PriceObservation,
    Seller,
    SourceAccount,
    SourcePost,
    TextEmbedding,
)


def all_listings(db: Session):
    from .visibility import visible_listings

    return visible_listings(db)


def prepare_snapshot(db):
    """Bound query count rather than one query per card and commercial field."""
    listings = all_listings(db)
    sellers = {seller.id: seller for seller in db.scalars(select(Seller)).all()}
    prices = {}
    for price in db.scalars(
        select(PriceObservation)
        .where(
            PriceObservation.component == "bouquet",
            PriceObservation.superseded.is_(False),
            PriceObservation.kind != "previous",
        )
        .order_by(PriceObservation.advertised_at.desc(), PriceObservation.created_at.desc(), PriceObservation.id.desc())
    ).all():
        listing = next((listing for listing in listings if listing.id == price.listing_id), None)
        if listing and (
            price.id in listing.attributes.get("accepted_price_ids", [])
            if "accepted_price_ids" in listing.attributes
            else price.reviewed
        ):
            prices.setdefault(price.listing_id, price)
    availability = {}
    for observation in db.scalars(
        select(AvailabilityObservation).order_by(AvailabilityObservation.created_at.desc())
    ).all():
        availability.setdefault(observation.listing_id, observation)
    posts = {}
    account_sellers = {account.id: account.seller_id for account in db.scalars(select(SourceAccount))}
    listing_sellers = {listing.id: listing.seller_id for listing in listings}
    for listing_id, post in db.execute(
        select(ListingSource.listing_id, SourcePost)
        .select_from(ListingSource)
        .join(PostVersion, PostVersion.id == ListingSource.version_id)
        .join(SourcePost, SourcePost.id == PostVersion.post_id)
        .order_by(SourcePost.published_at.desc())
    ).all():
        if account_sellers.get(post.account_id) == listing_sellers.get(listing_id):
            posts.setdefault(listing_id, post)
    db.info["catalog_snapshot"] = {
        "ids": {listing.id for listing in listings},
        "sellers": sellers,
        "prices": prices,
        "availability": availability,
        "posts": posts,
    }
    return listings


def current_price(db: Session, listing_id: str):
    snapshot = db.info.get("catalog_snapshot")
    if snapshot and listing_id in snapshot["ids"]:
        return snapshot["prices"].get(listing_id)
    statement = select(PriceObservation)
    listing = db.get(Listing, listing_id)
    if listing and "accepted_price_ids" in listing.attributes:
        statement = statement.where(PriceObservation.id.in_(listing.attributes["accepted_price_ids"]))
    elif listing and listing.state in {"published", "provisional"}:
        statement = statement.where(PriceObservation.reviewed.is_(True))
    return db.scalar(
        statement.where(
            PriceObservation.listing_id == listing_id,
            PriceObservation.component == "bouquet",
            PriceObservation.superseded.is_(False),
            PriceObservation.kind != "previous",
        )
        .order_by(PriceObservation.advertised_at.desc(), PriceObservation.created_at.desc(), PriceObservation.id.desc())
        .limit(1)
    )


def price_json(price):
    if price is None:
        return None
    return {
        "id": price.id,
        "amount_min": price.amount_min,
        "amount_max": price.amount_max,
        "currency": price.currency,
        "kind": price.kind,
        "component": price.component,
        "reviewed": price.reviewed,
        "advertised_at": aware(price.advertised_at).isoformat(),
        "observed_at": aware(price.created_at).isoformat(),
        "valid_until": aware(price.valid_until).isoformat() if price.valid_until else None,
        "evidence": price.evidence,
    }


def card(db: Session, listing: Listing):
    from .visibility import public_attributes, public_composition

    seller = db.get(Seller, listing.seller_id)
    price = current_price(db, listing.id)
    snapshot = db.info.get("catalog_snapshot")
    availability = (
        snapshot["availability"].get(listing.id)
        if snapshot and listing.id in snapshot["ids"]
        else db.scalar(
            select(AvailabilityObservation)
            .where(AvailabilityObservation.listing_id == listing.id)
            .order_by(AvailabilityObservation.created_at.desc())
            .limit(1)
        )
    )
    post = (
        snapshot["posts"].get(listing.id)
        if snapshot and listing.id in snapshot["ids"]
        else db.scalar(
            select(SourcePost)
            .join(PostVersion, PostVersion.post_id == SourcePost.id)
            .join(ListingSource, ListingSource.version_id == PostVersion.id)
            .join(SourceAccount, SourceAccount.id == SourcePost.account_id)
            .where(ListingSource.listing_id == listing.id)
            .where(SourceAccount.seller_id == listing.seller_id)
            .order_by(SourcePost.published_at.desc())
            .limit(1)
        )
    )
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "primary_flower": listing.primary_flower,
        "color": listing.color,
        "arrangement": listing.arrangement,
        "stem_count": listing.stem_count,
        "image_path": listing.image_path,
        "style": listing.style,
        "occasion": listing.occasion,
        "state": listing.state,
        "attributes": public_attributes(listing),
        "composition": public_composition(listing),
        "offer_type": listing.attributes.get("offer_type", "seller_work"),
        "updating": bool(listing.attributes.get("updating")),
        "capture_complete": listing.attributes.get("capture_complete"),
        "evidence_at": listing.attributes.get("evidence_at"),
        "is_demo": listing.is_demo,
        "seller": {
            "id": seller.id,
            "name": seller.name,
            "slug": seller.slug,
            "district": seller.district,
            "city": seller.city,
        },
        "price": price_json(price),
        "availability": listing.attributes.get("accepted_availability")
        or {
            "status": availability.status if availability else "unknown",
            "lead_days": availability.lead_days if availability else None,
            "delivery": availability.delivery if availability else None,
        },
        "published_at": aware(post.published_at).isoformat() if post and post.published_at else None,
        "last_checked_at": aware(post.last_seen_at).isoformat() if post else None,
        "source_url": post.url if post else None,
        "source_platform": post.platform if post else None,
        "source_state": post.access_state if post else None,
    }


SYNONYMS = {
    "hoa hong": "rose",
    "hong": "pink",
    "trang": "white",
    "vang": "yellow",
    "huong duong": "sunflower",
    "cat tuong": "lisianthus",
    "bo hoa": "bouquet",
    "sinh nhat": "birthday",
    "lan man": "romantic",
    "tulips": "tulip",
    "roses": "rose",
}


def normalized_search(value: str):
    result = fold(value)
    for source, target in SYNONYMS.items():
        result = re.sub(rf"\b{re.escape(source)}\b", target, result)
    return result


def demo_vector(text: str):
    """Only for clearly marked synthetic fixtures; never used for live source content."""
    vector = [0.0] * 1536
    for word in re.findall(r"\w+", normalized_search(text)):
        digest = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % 1536] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]


def cosine(a, b):
    denominator = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0


def catalog(
    db: Session,
    q="",
    flower="",
    color="",
    district="",
    arrangement="",
    occasion="",
    delivery=None,
    max_price=None,
    min_price=None,
    sort="recommended",
    cursor=None,
    limit=24,
    flower_mode="any",
    reviewed_only=False,
):
    listings = prepare_snapshot(db)
    query = normalized_search(q)
    tokens = query.split()
    rows = []
    from .visibility import flower_types

    requested_flowers = {part.strip() for part in flower.split(",") if part.strip()}
    if len(requested_flowers) > 12 or flower_mode not in {"any", "all"}:
        raise ValueError("Choose up to twelve flowers with ANY or ALL matching")
    for listing in listings:
        row = card(db, listing)
        if (
            requested_flowers
            and not (
                requested_flowers <= flower_types(listing)
                if flower_mode == "all"
                else requested_flowers & flower_types(listing)
            )
            or color
            and row["color"] != color
            or district
            and row["seller"]["district"] != district
            or arrangement
            and row["arrangement"] != arrangement
            or occasion
            and row["occasion"] != occasion
        ):
            continue
        if reviewed_only and not listing.attributes.get("extraction_reviewed"):
            continue
        if delivery is not None and row["availability"]["delivery"] is not delivery:
            continue
        p = row["price"]
        if max_price is not None and (p is None or p["currency"] != "VND" or p["amount_min"] > max_price):
            continue
        if min_price is not None and (
            p is None or p["currency"] != "VND" or (p["amount_max"] or p["amount_min"]) < min_price
        ):
            continue
        searchable = normalized_search(
            listing.search_text + " " + row["seller"]["name"] + " " + row["seller"]["district"]
        )
        lexical = sum(token in searchable for token in tokens) / max(1, len(tokens))
        row["search_score"] = lexical
        rows.append(row)
    # RRF fuses lexical ranks and stored demo semantic vectors. Live vectors use the configured API provider.
    search_mode = "keyword"
    if query:
        from .providers import query_embedding

        vector, model = query_embedding(db, query)
        if vector is not None:
            semantic = []
            candidate_ids = {row["id"] for row in rows}
            candidates = [listing for listing in listings if listing.id in candidate_ids]
            if db.bind.dialect.name == "postgresql" and candidate_ids:
                # Exact filtered pgvector scan. HNSW is intentionally deferred until recall is measured.
                distance = cast(TextEmbedding.vector, Vector(1536)).cosine_distance(vector)
                semantic = [
                    (listing_id, 1 - float(value))
                    for listing_id, value in db.execute(
                        select(Listing.id, distance)
                        .join(TextEmbedding, TextEmbedding.revision_id == Listing.current_revision_id)
                        .where(Listing.id.in_(candidate_ids), TextEmbedding.model_version == model, distance < 0.85)
                        .order_by(distance, Listing.id)
                    ).all()
                ]
                # The simple dictionary preserves Vietnamese terms; aliases were normalized above.
                fts = func.to_tsvector("simple", Listing.search_text)
                rank = func.ts_rank_cd(fts, func.plainto_tsquery("simple", query))
                full_text = dict(db.execute(select(Listing.id, rank).where(Listing.id.in_(candidate_ids))).all())
                for row in rows:
                    row["search_score"] = max(row["search_score"], float(full_text.get(row["id"], 0)))
            else:
                vectors = {
                    e.revision_id: e.vector
                    for e in db.scalars(select(TextEmbedding).where(TextEmbedding.model_version == model)).all()
                }
                for listing in candidates:
                    if listing.current_revision_id in vectors:
                        score = cosine(vector, vectors[listing.current_revision_id])
                        if score > 0.15:
                            semantic.append((listing.id, score))
            semantic.sort(key=lambda item: (-item[1], item[0]))
            semantic_rank = {item[0]: rank + 1 for rank, item in enumerate(semantic)}
            lexical_rank = {
                row["id"]: rank + 1
                for rank, row in enumerate(
                    sorted(
                        [row for row in rows if row["search_score"] > 0],
                        key=lambda row: (-row["search_score"], row["id"]),
                    )
                )
            }
            for row in rows:
                row["search_score"] = (1 / (60 + lexical_rank[row["id"]]) if row["id"] in lexical_rank else 0) + (
                    1 / (60 + semantic_rank[row["id"]]) if row["id"] in semantic_rank else 0
                )
            search_mode = "demo-hybrid" if model.startswith("demo") else "hybrid"
        rows = [row for row in rows if row["search_score"] > 0]
    if sort == "price-asc":
        rows.sort(
            key=lambda r: (
                r["price"]["amount_min"] if r["price"] and r["price"]["currency"] == "VND" else float("inf"),
                r["id"],
            )
        )
    elif sort == "price-desc":
        rows.sort(
            key=lambda r: (
                -(r["price"]["amount_min"]) if r["price"] and r["price"]["currency"] == "VND" else float("inf"),
                r["id"],
            )
        )
    elif sort == "freshest":
        rows.sort(key=lambda r: (r["published_at"] or "", r["id"]), reverse=True)
    else:
        rows.sort(key=lambda r: (-r["search_score"], r["id"]))
    total = len(rows)
    signature = hashlib.sha256(
        json.dumps(
            [
                q,
                flower,
                color,
                district,
                arrangement,
                occasion,
                delivery,
                min_price,
                max_price,
                sort,
                flower_mode,
                reviewed_only,
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()[:16]
    start = 0
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if decoded["signature"] != signature:
                raise ValueError("Cursor does not match filters")
            positions = [index for index, r in enumerate(rows) if r["id"] == decoded["after"]]
            if not positions:
                raise ValueError("Cursor record changed; restart pagination")
            start = positions[0] + 1
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid or outdated catalog cursor") from exc
    page = rows[start : start + limit]
    next_cursor = (
        base64.urlsafe_b64encode(json.dumps({"after": page[-1]["id"], "signature": signature}).encode())
        .decode()
        .rstrip("=")
        if start + limit < total and page
        else None
    )
    return {"items": page, "total": total, "next_cursor": next_cursor, "search_mode": search_mode}


def similarity(a: Listing, b: Listing):
    fields = [("primary_flower", 0.18), ("arrangement", 0.10), ("stem_count", 0.12), ("color", 0.10), ("style", 0.10)]
    score, reasons = 0.0, []
    for name, weight in fields:
        av, bv = getattr(a, name), getattr(b, name)
        if av is not None and bv is not None:
            match = max(0, 1 - abs(av - bv) / max(av, bv)) if name == "stem_count" else float(av == bv)
            score += weight * match
            if match >= 0.8:
                reasons.append(
                    {
                        "primary_flower": "Same primary flower",
                        "arrangement": "Same arrangement",
                        "stem_count": "Similar stated stem count",
                        "color": "Same primary color",
                        "style": "Similar style",
                    }[name]
                )
    from .visibility import flower_types

    a_types, b_types = flower_types(a), flower_types(b)
    if a_types and b_types:
        score += 0.12 * len(a_types & b_types) / len(a_types | b_types)
        if a_types & b_types:
            reasons.append("Shared supported flower composition")
    return score, reasons


def selected_image_vectors(db, candidates):
    from .models import ListingRevision

    selected = {listing.id: listing for listing in candidates}
    images = {}
    for listing_id, embedding in db.execute(
        select(ListingSource.listing_id, ImageEmbedding)
        .select_from(ListingSource)
        .join(PostMedia, PostMedia.version_id == ListingSource.version_id)
        .join(ImageEmbedding, ImageEmbedding.media_id == PostMedia.media_id)
    ).all():
        listing = selected.get(listing_id)
        if not listing:
            continue
        if listing.attributes.get("offer_id"):
            revision = db.get(ListingRevision, listing.current_revision_id) if listing.current_revision_id else None
            if (
                not revision
                or embedding.media_id not in revision.snapshot.get("media_ids", [])
                or embedding.media_id in revision.snapshot.get("media_regions", {})
            ):
                # Whole-post/carousel vectors cannot stand in for a selected product crop.
                continue
        images.setdefault(listing_id, []).append(embedding)
    return images


def similar(db: Session, target: Listing, limit=12):
    rows = []
    candidates = prepare_snapshot(db)
    images = selected_image_vectors(db, candidates)
    texts = {entry.revision_id: entry for entry in db.scalars(select(TextEmbedding)).all()}
    for listing in candidates:
        if listing.id == target.id:
            continue
        score, reasons = similarity(target, listing)
        image_pairs = [
            (a, b)
            for a in images.get(target.id, [])
            for b in images.get(listing.id, [])
            if a.model_version == b.model_version
        ]
        visual = max((max(0, cosine(a.vector, b.vector)) for a, b in image_pairs), default=0)
        a, b = texts.get(target.current_revision_id), texts.get(listing.current_revision_id)
        semantic = max(0, cosine(a.vector, b.vector)) if a and b and a.model_version == b.model_version else 0
        # Attribute weights total .60; keep full-weight denominator when a modality is absent.
        score = score * (0.50 / 0.72) + 0.35 * visual + 0.15 * semantic
        if visual > 0.8:
            reasons.append("Similar image features" if not target.is_demo else "Matching demonstration photo category")
        rows.append(
            {
                **card(db, listing),
                "similarity": round(score, 3),
                "match_reasons": reasons,
                "matching_method": "demo-hybrid"
                if target.is_demo
                else "hybrid"
                if image_pairs
                else "attributes-and-text"
                if semantic
                else "attributes",
                "score_components": {"visual": visual, "semantic": semantic, "missing_modalities_reduce_score": True},
                "qualified": eligibility(db, target, listing)[0],
            }
        )
    return sorted(rows, key=lambda r: (-r["similarity"], r["id"]))[:limit]


def commercial_issues(db: Session, listing: Listing):
    reasons = []
    p = current_price(db, listing.id)
    if listing.state != "published":
        reasons.append("Listing is not published")
    from .visibility import visible

    if not visible(db, listing):
        reasons.append("Supporting evidence is unavailable")
    if listing.attributes.get("updating"):
        reasons.append("New evidence is being processed")
    if card(db, listing).get("source_state") not in {None, "accessible"}:
        reasons.append("Original source is currently unavailable")
    if listing.attributes.get("offer_type") == "recreation_quote":
        reasons.append("Recreation quotations are outside strict benchmarks")
    if listing.primary_flower == "mixed" and not listing.attributes.get("composition_reviewed"):
        reasons.append("Mixed composition requires commercial review")
    if not p:
        reasons.append("No advertised bouquet price")
    else:
        if p.currency != "VND":
            reasons.append("Different currency")
        if p.kind not in {"exact", "promotion"} or p.amount_min != p.amount_max:
            reasons.append("Price is a range or starting price")
        if not p.reviewed:
            reasons.append("Commercial evidence has not been reviewed")
        if aware(p.advertised_at) < utcnow() - timedelta(days=30) and not (
            p.valid_until and aware(p.valid_until) > utcnow()
        ):
            reasons.append("Advertisement is older than 30 days")
        if p.valid_until and aware(p.valid_until) < utcnow():
            reasons.append("Offer expired")
    if not listing.primary_flower or not listing.color or not listing.arrangement:
        reasons.append("Insufficient configuration evidence")
    if not listing.stem_count or not listing.attributes.get("size_reviewed"):
        reasons.append("Comparable size is not supported by reviewed evidence")
    return reasons


def eligibility(db: Session, target: Listing, candidate: Listing):
    reasons = commercial_issues(db, candidate)
    if target.seller_id == candidate.seller_id:
        reasons.append("Same seller")
    target_composition = set(target.attributes.get("flower_composition") or [target.primary_flower])
    candidate_composition = set(candidate.attributes.get("flower_composition") or [candidate.primary_flower])
    if target.primary_flower == "mixed" or candidate.primary_flower == "mixed":
        if (
            not target.attributes.get("composition_reviewed")
            or not candidate.attributes.get("composition_reviewed")
            or target_composition != candidate_composition
        ):
            reasons.append("Mixed composition equivalence is not reviewed")
    if len(target_composition & candidate_composition) / max(1, len(target_composition | candidate_composition)) < 0.6:
        reasons.append("Flower composition differs materially")
    for name, message in [
        ("arrangement", "Different arrangement"),
        ("primary_flower", "Different primary flower"),
        ("color", "Different primary color"),
    ]:
        if getattr(target, name) != getattr(candidate, name):
            reasons.append(message)
    if (
        target.stem_count
        and candidate.stem_count
        and abs(candidate.stem_count - target.stem_count) / target.stem_count > 0.2
    ):
        reasons.append("Stated stem count differs by more than 20%")
    if db.get(Seller, target.seller_id).city != db.get(Seller, candidate.seller_id).city:
        reasons.append("Different market")
    # Fictional records must never participate in a live benchmark.
    if target.is_demo != candidate.is_demo:
        reasons.append("Demonstration and live records cannot be mixed")
    return not reasons, reasons


def comparison(db: Session, target: Listing, persist=True):
    prepare_snapshot(db)
    target_issues = commercial_issues(db, target)
    by_seller, excluded = {}, []
    for candidate in all_listings(db):
        if candidate.id == target.id:
            continue
        qualified, reasons = eligibility(db, target, candidate)
        if not qualified or target_issues:
            excluded.append(
                {"listing_id": candidate.id, "reasons": reasons or ["Selected bouquet is not benchmark eligible"]}
            )
            continue
        score, _ = similarity(target, candidate)
        old = by_seller.get(candidate.seller_id)
        if old is None or (-score, candidate.id) < (-old[0], old[1].id):
            by_seller[candidate.seller_id] = (score, candidate)
    members = sorted([v[1] for v in by_seller.values()], key=lambda item: item.id)
    values = [current_price(db, item.id).amount_min for item in members]
    n = len(values)
    target_price = current_price(db, target.id)
    reference = median(values) if n >= 5 else None
    quartiles = quantiles(values, n=4, method="inclusive") if n >= 10 else None
    summary = {
        "status": "ineligible" if target_issues else "insufficient" if n < 5 else "limited" if n < 10 else "qualified",
        "seller_count": n,
        "listing_count": n,
        "median": reference,
        "min": min(values) if n >= 5 else None,
        "max": max(values) if n >= 5 else None,
        "q1": quartiles[0] if quartiles else None,
        "q3": quartiles[2] if quartiles else None,
        "percentile": 100
        * (sum(v < target_price.amount_min for v in values) + 0.5 * sum(v == target_price.amount_min for v in values))
        / n
        if n >= 10
        else None,
        "relative_difference": (target_price.amount_min - reference) / reference
        if reference and target_price
        else None,
        "currency": "VND",
        "window_days": 30,
        "target_issues": target_issues,
        "is_demo": target.is_demo,
        "caveat": "Sample of indexed advertisements, not a representative Hanoi market estimate.",
        "algorithm_version": "cohort-v1",
    }
    if persist:
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "summary": summary,
                    "target_revision": target.current_revision_id,
                    "members": [(item.id, current_price(db, item.id).id, item.current_revision_id) for item in members],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        recent = db.scalar(
            select(CohortRun)
            .where(CohortRun.listing_id == target.id, CohortRun.created_at > utcnow() - timedelta(minutes=5))
            .order_by(CohortRun.created_at.desc())
            .limit(1)
        )
        if recent and recent.definition.get("fingerprint") == fingerprint:
            summary["run_id"] = recent.id
            return {"summary": summary, "items": [card(db, item) for item in members], "excluded": excluded}
        run = CohortRun(
            listing_id=target.id,
            definition={
                "fingerprint": fingerprint,
                "arrangement": target.arrangement,
                "flower": target.primary_flower,
                "color": target.color,
                "stem_count": target.stem_count,
                "size_tolerance": 0.2,
                "window_days": 30,
                "seller_balanced": True,
                "target_seller_excluded": True,
            },
            summary=summary,
        )
        db.add(run)
        db.flush()
        for item in members:
            db.add(CohortMember(run_id=run.id, listing_id=item.id, price_id=current_price(db, item.id).id))
        db.commit()
        summary["run_id"] = run.id
    return {"summary": summary, "items": [card(db, item) for item in members], "excluded": excluded}
