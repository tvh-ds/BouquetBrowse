"""Synthetic native PostgreSQL/media restore proof, exclusively in fresh CI databases."""

import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

root = Path(__file__).resolve().parents[1]
base = make_url(os.environ["TEST_DATABASE_URL"])
if not (base.database or "").endswith("_test"):
    raise SystemExit("Synthetic recovery requires an isolated TEST_DATABASE_URL ending _test")
source_name, restore_name = "bouquetbrowse_backup_source_test", "bouquetbrowse_backup_restore_test"
admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    for name in [source_name, restore_name]:
        if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": name}):
            raise SystemExit("Recovery database already exists; refusing to replace it")
        connection.execute(text(f"CREATE DATABASE {connection.dialect.identifier_preparer.quote(name)}"))
admin.dispose()
folder = root / ".data" / f"ci-recovery-{uuid4().hex}"
folder.mkdir(parents=True)
source_url = base.set(database=source_name).render_as_string(hide_password=False)
restore_url = base.set(database=restore_name).render_as_string(hide_password=False)
os.environ.update(DATABASE_URL=source_url, APP_MODE="demo", MEDIA_DIR=str(folder / "source-media"),
                  OPENAI_API_KEY="", DISCOVERY_ENABLED="false", RECURRING_ENABLED="false", BACKUPS_ENABLED="false")

from bouquetbrowse.backups import create_backup  # noqa: E402
from bouquetbrowse.config import Settings  # noqa: E402
from bouquetbrowse.db import Base, utcnow  # noqa: E402
from bouquetbrowse.models import Listing, ListingSource, MediaAsset, PostMedia, PriceObservation  # noqa: E402
from bouquetbrowse.recovery import export_deletions, verify_manifest  # noqa: E402
from bouquetbrowse.seed import seed_demo  # noqa: E402
from bouquetbrowse.storage import put_media  # noqa: E402
from bouquetbrowse.worker import purge_listing  # noqa: E402

engine = create_engine(source_url)
with engine.begin() as connection:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(connection)
factory = sessionmaker(engine, expire_on_commit=False)
buffer = io.BytesIO()
Image.new("RGB", (100, 100), "pink").save(buffer, format="JPEG")
content = buffer.getvalue()
key = hashlib.sha256(content).hexdigest()+".jpg"
put_media(key, content)
with factory() as db:
    seed_demo(db)
    listing = db.scalar(select(Listing).order_by(Listing.id))
    listing_id = listing.id
    source = db.scalar(select(ListingSource).where(ListingSource.listing_id == listing_id))
    asset = MediaAsset(state="ready", storage_key=key, checksum=key[:-4], retention_until=utcnow()+timedelta(days=30))
    db.add(asset)
    db.flush()
    db.add(PostMedia(version_id=source.version_id, media_id=asset.id, position=999))
    db.commit()
settings = Settings(_env_file=None, database_url=source_url, backup_directory=folder / "backups")
result = create_backup(factory, settings)
manifest = settings.backup_directory / result["snapshot"] / result["manifest"]
assert verify_manifest(manifest)["media"]["objects"] == 1
with factory() as db:
    purge_listing(db, listing_id)
    db.commit()
    ledger = folder / "current-after-deletion.jsonl"
    assert export_deletions(db, ledger) > 0
environment = {**os.environ, "RESTORE_DATABASE_URL": restore_url}
process = subprocess.run([sys.executable, str(root / "deploy" / "restore_rehearsal.py"), str(manifest),
                          "--deletions", str(ledger), "--media-directory", str(folder / "restored-media")],
                         env=environment, capture_output=True, text=True, check=True, timeout=180)
report = json.loads(process.stdout.splitlines()[-1])
assert report["collection"] == "paused" and report["media_restored"] == 0
target = create_engine(restore_url)
with Session(target) as db:
    assert db.get(Listing, listing_id).state == "withdrawn"
    assert not list(db.scalars(select(PriceObservation).where(PriceObservation.listing_id == listing_id)))
    from bouquetbrowse.visibility import visible_listings

    assert listing_id not in {listing.id for listing in visible_listings(db)}
assert not list((folder / "restored-media").iterdir())
target.dispose()
engine.dispose()
print(json.dumps({"synthetic_postgres_restore": "passed", "later_deletion_replayed": True,
                  "deleted_media_restored": False, "live_collection": False, "elapsed_seconds": report["elapsed_seconds"]}))
