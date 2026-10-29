"""Native PostgreSQL backups with separate media and current deletion replay evidence."""

import io
import json
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url

from .config import get_settings
from .db import aware, utcnow
from .models import MediaAsset
from .pipeline import digest
from .providers import CapabilityError
from .recovery import (
    checksum,
    export_deletions,
    postgres_cli_connection,
    postgres_cli_environment,
    private_directory,
    verify_manifest,
)

OWNER = "BouquetBrowse managed backups v1"


def owned_directory(path):
    folder = private_directory(path)
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / ".bouquetbrowse-backups"
    if not marker.exists():
        if any(folder.iterdir()):
            raise ValueError("Backup directory is not empty and has no ownership marker")
        with marker.open("x", encoding="utf-8") as stream:
            stream.write(OWNER)
    if marker.is_symlink() or marker.read_text(encoding="utf-8") != OWNER:
        raise ValueError("Backup ownership marker is invalid")
    return folder


def archive_media(keys, target, check=None):
    from .storage import get_media_bytes, validate_key

    total = 0
    if len(keys) > 5000:
        raise ValueError("Pilot media backup exceeds 5,000 objects")
    with tarfile.open(fileobj=target, mode="w|") as archive:
        for key in keys:
            if check:
                check()
            validate_key(key)
            content = get_media_bytes(key)
            total += len(content)
            if len(content) > 10 * 1024 * 1024 or total > 10 * 1024**3:
                raise ValueError("Pilot media backup exceeds its byte allowance")
            member = tarfile.TarInfo(key)
            member.size, member.mode = len(content), 0o600
            archive.addfile(member, io.BytesIO(content))
    return {"objects": len(keys), "bytes": total}


def snapshot_deletions(factory, directory=None):
    root = owned_directory(get_settings().backup_directory) if directory is None else None
    folder = owned_directory(directory or (root / "current-deletions"))
    target = folder / "deletions-current.jsonl"
    temporary = folder / f"ledger-{uuid4()}.tmp"
    with factory() as db:
        count = export_deletions(db, temporary)
    # Only replace the application-owned ledger; never follow a link to another file.
    if target.is_symlink():
        raise ValueError("Deletion ledger target must be an ordinary managed file")
    temporary.replace(target)
    return {"records": count, "name": target.name}


def create_backup(factory, settings=None, runner=subprocess.run, lease=None):
    settings = settings or get_settings()

    def verify_lease():
        if lease:
            from .leases import guard

            with factory() as db:
                guard(db, lease)
                db.commit()

    verify_lease()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise CapabilityError(
            "Native recurring backup requires PostgreSQL and a matching pg_dump client.", "backup_postgres_required"
        )
    root = owned_directory(settings.backup_directory)
    identity = digest({"host": url.host, "port": url.port, "database": url.database, "username": url.username})
    if lease:
        for previous in root.glob("snapshot-*/manifest.json"):
            if previous.is_symlink() or previous.parent.is_symlink() or previous.resolve().parent.parent != root:
                raise ValueError("Backup receipt is outside the managed directory")
            saved = json.loads(previous.read_text(encoding="utf-8"))
            if saved.get("job_id") == lease.job_id and saved.get("database_identity") == identity:
                verify_manifest(previous)
                snapshot_deletions(factory, root / "current-deletions")
                return {
                    "snapshot": previous.parent.name,
                    "manifest": "manifest.json",
                    "media_objects": saved["media"]["objects"],
                    "elapsed_seconds": saved["elapsed_seconds"],
                    "reused": True,
                }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = root / f"snapshot-{stamp}-{uuid4().hex[:8]}"
    folder.mkdir()
    (folder / ".bouquetbrowse-backups").write_text(OWNER, encoding="utf-8")
    dump, media, ledger = folder / "database.dump", folder / "media.tar", folder / "deletions.jsonl"
    connection = postgres_cli_connection(url)
    started = utcnow()
    try:
        with dump.open("xb") as stream:
            runner(
                ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--dbname", connection],
                stdout=stream,
                stderr=subprocess.PIPE,
                env=postgres_cli_environment(url.password),
                timeout=600,
                check=True,
            )
        if dump.stat().st_size == 0:
            raise ValueError("Database dump is empty")
        with factory() as db:
            keys = list(
                db.scalars(
                    select(MediaAsset.storage_key)
                    .where(
                        MediaAsset.state == "ready",
                        MediaAsset.storage_key.is_not(None),
                        MediaAsset.retention_until > utcnow(),
                    )
                    .distinct()
                )
            )
            export_deletions(db, ledger)
        with media.open("xb") as stream:
            measured = archive_media(keys, stream, verify_lease)
        files = [
            {"name": file.name, "sha256": checksum(file), "bytes": file.stat().st_size}
            for file in [dump, media, ledger]
        ]
        manifest = {
            "version": "bouquet-backup-v1",
            "created_at": stamp,
            "files": files,
            "media": measured,
            "elapsed_seconds": (utcnow() - started).total_seconds(),
            "job_id": lease.job_id if lease else None,
            "database_identity": identity,
            "note": "Separate DB/media observations; replay the latest external deletion ledger before serving a restore",
        }
        path = folder / "manifest.json"
        verify_lease()
        with path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        snapshot_deletions(factory, settings.backup_directory / "current-deletions")
        prune_backups(root)
        return {
            "snapshot": folder.name,
            "manifest": "manifest.json",
            "media_objects": measured["objects"],
            "elapsed_seconds": manifest["elapsed_seconds"],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        # Do not expose native connection diagnostics, environment or credentials through jobs/logs.
        raise CapabilityError(
            "Backup failed. Check pg_dump version, database connectivity and private disk space.", "backup_failed"
        ) from exc


def prune_backups(root, now=None):
    import re

    root = owned_directory(root)
    now = now or utcnow()
    removed = 0
    for folder in root.glob("snapshot-*"):
        if folder.is_symlink() or folder.resolve().parent != root or not folder.is_dir():
            raise ValueError("Refusing an unmanaged backup retention target")
        marker, manifest = folder / ".bouquetbrowse-backups", folder / "manifest.json"
        match = re.fullmatch(r"snapshot-(\d{8}T\d{6}Z)-[0-9a-f]{8}", folder.name)
        if not match:
            raise ValueError("Unknown managed backup folder name")
        created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if aware(created) > now - timedelta(days=7):
            continue
        if not marker.is_file() or marker.read_text(encoding="utf-8") != OWNER:
            raise ValueError("Snapshot ownership evidence is missing")
        if manifest.is_file():
            data = verify_manifest(manifest)
            expected = {r["name"] for r in data["files"]} | {"manifest.json", ".bouquetbrowse-backups"}
        else:
            # Incomplete private dumps have the same seven-day retention bound.
            expected = {p.name for p in folder.iterdir()}
            if expected - {"database.dump", "media.tar", "deletions.jsonl", ".bouquetbrowse-backups"}:
                raise ValueError("Incomplete snapshot contains unowned files")
        if {p.name for p in folder.iterdir()} != expected or any(p.is_symlink() for p in folder.iterdir()):
            raise ValueError("Snapshot contains unowned files; retention stopped")
        for file in folder.iterdir():
            file.unlink()
        folder.rmdir()
        removed += 1
    return removed
