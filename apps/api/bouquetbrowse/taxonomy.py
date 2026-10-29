"""Immutable reviewed vocabularies; aliases are literals, never executable patterns."""

import re

from sqlalchemy import select

from .conversation_models import TaxonomyTerm
from .extraction import FLOWERS, fold


def vocabulary(db, version="flowers-v2"):
    values = {key: [key] for key in FLOWERS}
    for row in db.scalars(
        select(TaxonomyTerm).where(TaxonomyTerm.taxonomy_version == version, TaxonomyTerm.state == "accepted")
    ):
        values[row.key] = sorted(set([row.key, *row.aliases]))
    return values


def normalize(db, label, version="flowers-v2"):
    matches = [key for key, aliases in vocabulary(db, version).items() if fold(label) in {fold(a) for a in aliases}]
    return matches[0] if len(matches) == 1 else None


def flower_patterns(db, version="flowers-v2"):
    result = dict(FLOWERS)
    for key, aliases in vocabulary(db, version).items():
        literals = "|".join(re.escape(alias) for alias in aliases)
        result[key] = "|".join(filter(None, [result.get(key), rf"(?<!\w)(?:{literals})(?!\w)"]))
    return result


def promote(db, term, version, aliases, actor, reason, canonical_key=None):
    from .discovery import settings_row
    from .runtime_models import DiscoverySettings

    settings = settings_row(db)
    settings = db.scalar(
        select(DiscoverySettings)
        .where(DiscoverySettings.id == settings.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if settings.configuration.get("taxonomy_version", "flowers-v2") != term.taxonomy_version:
        raise ValueError("Proposal targets an older taxonomy; rebase it before promotion")
    canonical_key = canonical_key or term.key
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", canonical_key):
        raise ValueError("Choose a stable lowercase category key")
    if term.state != "proposed" or version in {term.taxonomy_version, "flowers-v2"}:
        raise ValueError("Only a pending proposal may create a new taxonomy version")
    if db.scalar(select(TaxonomyTerm.id).where(TaxonomyTerm.taxonomy_version == version)):
        raise ValueError("Taxonomy versions are immutable; choose a new version")
    values = vocabulary(db, term.taxonomy_version)
    aliases = sorted(set([term.key, *values.get(canonical_key, []), *aliases]))
    for alias in aliases:
        if not alias.strip() or len(alias) > 80 or any(c in alias for c in "\r\n\x00"):
            raise ValueError("Aliases must be bounded single-line literal names")
        if any(key != canonical_key and fold(alias) in {fold(a) for a in names} for key, names in values.items()):
            raise ValueError("An alias cannot name two flower types")
    values[canonical_key] = aliases
    for key, names in values.items():
        db.add(
            TaxonomyTerm(
                taxonomy_version=version,
                key=key,
                aliases=names,
                state="accepted",
                evaluation={
                    "actor": actor,
                    "reason": reason,
                    "source_version": term.taxonomy_version,
                    "visual_support": "requires_configuration_specific_benchmark",
                },
            )
        )
    term.state = "accepted_proposal"
    term.evaluation = {**term.evaluation, "actor": actor, "reason": reason, "promoted_version": version}
    # Future executions adopt this version. Existing executions and cached results remain pinned.
    settings.configuration = {**settings.configuration, "taxonomy_version": version}
    settings.version += 1
    affected = reprocess_affected(db, aliases, version)
    term.evaluation = {**term.evaluation, "affected_offers": affected}
    return version


def reprocess_affected(db, aliases, version):
    from .conversation_models import OfferAssociation, OfferOccurrence
    from .db import aware, utcnow
    from .executions import create_execution
    from .leases import cancel
    from .models import Listing, PostVersion
    from .pilot import offer_configuration
    from .runtime_models import GraphExecution

    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)", re.I)
    affected = set()
    for offer, association, source in db.execute(
        select(OfferOccurrence, OfferAssociation, PostVersion)
        .join(OfferAssociation, OfferAssociation.offer_id == OfferOccurrence.id)
        .join(PostVersion, PostVersion.id == OfferAssociation.version_id)
        .where(OfferOccurrence.state.not_in(["withdrawn", "expired", "rejected"]))
    ).all():
        if (
            association.revision != offer.association_revision
            or aware(source.retention_until) <= utcnow()
            or not pattern.search(source.caption)
        ):
            continue
        if offer.id in affected:
            continue
        affected.add(offer.id)
        configuration = offer_configuration({"taxonomy_version": version})
        execution = create_execution(
            db, "offer", f"taxonomy:{offer.id}:{version}", configuration, offer.input_fingerprint, offer.id
        )
        for previous in db.scalars(
            select(GraphExecution).where(
                GraphExecution.offer_id == offer.id,
                GraphExecution.kind == "offer",
                GraphExecution.id != execution.id,
                GraphExecution.state.not_in(["completed", "withdrawn", "superseded", "cancelled"]),
            )
        ):
            cancel(db, previous.job_id)
            previous.state, previous.stop_reason = "superseded", "taxonomy_revision"
        if offer.listing_id:
            listing = db.get(Listing, offer.listing_id)
            listing.attributes = {**listing.attributes, "updating": True}
    return sorted(affected)
