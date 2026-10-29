"""Exercise both fresh installs and upgrades with populated historical tables."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from runpy import run_path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from bouquetbrowse.conversation_models import OfferOccurrence
from bouquetbrowse.conversations import backfill_legacy
from bouquetbrowse.models import Listing
from bouquetbrowse.seed import seed_demo

MIGRATIONS = Path(__file__).parents[1] / "migrations"


def revision(name):
    spec = spec_from_file_location(name, MIGRATIONS / "versions" / f"{name}.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_populated_legacy_upgrade_preserves_urls_and_source_links(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    with engine.begin() as connection:
        legacy = run_path(str(MIGRATIONS / "legacy_schema.py"))
        legacy["Base"].metadata.create_all(connection)
        # Seed through legacy mappers, not today's mappers with today's columns.
        with Session(bind=connection) as db:
            seller = legacy["Seller"](name="Fictional migration seller", slug="migration-seller", district="Tay Ho")
            db.add(seller)
            db.flush()
            account = legacy["SourceAccount"](seller_id=seller.id, platform="threads", username="migration_seller")
            db.add(account)
            db.flush()
            from bouquetbrowse.db import utcnow

            post = legacy["SourcePost"](
                account_id=account.id,
                platform="threads",
                platform_post_id="legacy-post",
                published_at=utcnow(),
                url="https://www.threads.com/@fictional/post/legacy-post",
            )
            db.add(post)
            db.flush()
            version = legacy["PostVersion"](
                post_id=post.id,
                content_hash="old-hash",
                caption="Fictional roses",
                payload={},
                retention_until=utcnow(),
            )
            listing = legacy["Listing"](seller_id=seller.id, configuration_key="old-config", title="Fictional bouquet")
            db.add_all([version, listing])
            db.flush()
            listing_id, version_id = listing.id, version.id
            db.add(legacy["ListingSource"](listing_id=listing.id, version_id=version.id))
            db.flush()
        with Operations.context(MigrationContext.configure(connection)):
            revision("20261029_0002_conversations").upgrade()
        with Session(bind=connection) as db:
            assert db.get(Listing, listing_id).title == "Fictional bouquet"
            offer = db.scalar(select(OfferOccurrence))
            assert offer.listing_id == listing_id
            assert db.scalar(select(legacy["ListingSource"].version_id)) == version_id
            backfill_legacy(db)
            db.flush()
            assert len(list(db.scalars(select(OfferOccurrence)))) == 1
    engine.dispose()


def test_fresh_upgrade_downgrade_upgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    first, second = revision("20261023_0001_initial"), revision("20261029_0002_conversations")
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        first.upgrade()
        assert "offer_occurrences" not in inspect(connection).get_table_names()
        second.upgrade()
        second.downgrade()
        first.downgrade()
        assert not inspect(connection).get_table_names()
        first.upgrade()
        second.upgrade()
        with Session(bind=connection) as db:
            seed_demo(db)
            backfill_legacy(db)
            db.flush()
            assert db.scalar(select(OfferOccurrence)) is not None
    engine.dispose()


def test_runtime_migration_round_trip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    revisions = [
        revision(name) for name in ["20261023_0001_initial", "20261029_0002_conversations", "20261029_0003_runtime"]
    ]
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        for item in revisions:
            item.upgrade()
        assert "model_calls" in inspect(connection).get_table_names()
        assert "lease_token" in {column["name"] for column in inspect(connection).get_columns("jobs")}
        for item in reversed(revisions):
            item.downgrade()
        assert not inspect(connection).get_table_names()
    engine.dispose()
