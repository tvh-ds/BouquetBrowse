"""Restore only into a precreated, empty *_restore_test database and a new private media directory.

Requires native pg_restore matching the backup server. Never modifies live Storage.
"""

import argparse
import json
import os
import subprocess
import tarfile
import time
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from bouquetbrowse import models  # noqa: F401
from bouquetbrowse.config import get_settings
from bouquetbrowse.db import utcnow
from bouquetbrowse.models import MediaAsset
from bouquetbrowse.recovery import private_directory, replay_deletions, verify_manifest
from bouquetbrowse.retention import delete_checkpoints
from bouquetbrowse.runtime_models import GraphExecution
from bouquetbrowse.storage import validate_key


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--deletions", type=Path, required=True, help="Current separately retained deletion ledger")
    parser.add_argument("--media-directory", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_manifest(args.manifest)
    target = make_url(os.environ.get("RESTORE_DATABASE_URL", ""))
    if not target.drivername.startswith("postgresql") or not (target.database or "").endswith("_restore_test"):
        raise SystemExit("RESTORE_DATABASE_URL must identify an isolated PostgreSQL database ending _restore_test.")
    if target.database == make_url(get_settings().database_url).database:
        raise SystemExit("A rehearsal must not use the application's configured database.")
    engine = create_engine(target)
    if inspect(engine).get_table_names():
        raise SystemExit("The isolated rehearsal database must be empty. No existing tables will be replaced.")
    folder = private_directory(args.media_directory)
    if folder.exists():
        raise SystemExit("Use a new media rehearsal directory; existing files are never replaced.")
    files = {Path(row["name"]).suffix: args.manifest.resolve().parent / row["name"] for row in manifest["files"]}
    if ".dump" not in files or ".tar" not in files:
        raise SystemExit("Manifest requires separate database and media artifacts.")
    environment = {**os.environ, "PGPASSWORD": target.password or ""}
    connection = target.set(drivername="postgresql", password=None).render_as_string(hide_password=False)
    subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--dbname", connection, str(files[".dump"])], env=environment, check=True)
    if args.deletions.stat().st_size > 20 * 1024 * 1024:
        raise SystemExit("Deletion ledger exceeds 20 MB.")
    values = [json.loads(line) for line in args.deletions.read_text(encoding="utf-8").splitlines() if line.strip()]
    with Session(engine) as db:
        replayed = replay_deletions(db, values)
        from bouquetbrowse.retention import expire
        expire(db)
        # A restored collector must remain paused, with no queued social/model work.
        from bouquetbrowse.runtime_models import DiscoverySettings
        from bouquetbrowse.leases import cancel
        from bouquetbrowse.models import Job
        for settings in db.scalars(select(DiscoverySettings)):
            settings.paused, settings.version = True, settings.version + 1
        for execution in db.scalars(select(GraphExecution)):
            cancel(db, execution.job_id)
            execution.state, execution.stop_reason = "cancelled", "restore_rehearsal"
            delete_checkpoints(db, execution.id)
        for job in db.scalars(select(Job)):
            if job.kind not in {"delete-media", "delete-checkpoints"}:
                cancel(db, job.id)
        allowed = set(db.scalars(select(MediaAsset.storage_key).where(MediaAsset.state == "ready", MediaAsset.retention_until > utcnow())))
        db.commit()
    folder.mkdir(parents=True)
    copied, count = 0, 0
    with tarfile.open(files[".tar"], "r:") as archive:
        for member in archive:
            count += 1
            if count > 100000 or not member.isfile() or member.size > 10 * 1024 * 1024:
                raise SystemExit("Invalid or oversized media archive member.")
            key = validate_key(member.name)
            if key not in allowed:
                continue
            target_file = (folder / key).resolve()
            if target_file.parent != folder or target_file.exists():
                raise SystemExit("Media restore target is not a new managed file.")
            source = archive.extractfile(member)
            with target_file.open("xb") as output:
                output.write(source.read(10 * 1024 * 1024 + 1))
            copied += 1
    print(json.dumps({"rehearsal": "isolated", "deletion_records_replayed": replayed, "media_restored": copied,
                      "collection": "paused", "live_storage_modified": False, "elapsed_seconds": round(time.monotonic() - started, 2),
                      "note": "Verify application reads with the isolated target before claiming RPO/RTO. Reapply runtime grants before deployment."}))
    engine.dispose()


if __name__ == "__main__":
    main()
