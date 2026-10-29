"""Private, checksummed backups and content-free deletion replay for isolated restores."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from .config import ROOT
from .operations_models import DeletionRecord


def private_directory(path):
    folder = Path(path).resolve()
    if folder.is_relative_to(ROOT) and not folder.is_relative_to(ROOT / ".data"):
        raise ValueError("Keep backups and research exports under ignored .data or outside the public repository")
    return folder


def checksum(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def export_deletions(db, path):
    target = private_directory(Path(path).parent) / Path(path).name
    records = [
        {"subject_kind": r.subject_kind, "subject_id": r.subject_id, "reason": r.reason}
        for r in db.scalars(select(DeletionRecord).order_by(DeletionRecord.created_at))
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    return len(records)


def verify_manifest(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != "bouquet-backup-v1" or not data.get("files"):
        raise ValueError("Unknown or empty backup manifest")
    for record in data["files"]:
        candidate = (path.parent / record["name"]).resolve()
        if candidate.parent != path.parent or candidate.is_symlink() or not candidate.is_file():
            raise ValueError("Backup members must be ordinary files in the manifest directory")
        if checksum(candidate) != record["sha256"] or candidate.stat().st_size != record["bytes"]:
            raise ValueError("Backup checksum or size mismatch")
    return data


def replay_deletions(db, values):
    from .models import Listing, PostVersion
    from .retention import ledger, scrub_versions
    from .worker import purge_listing

    if len(values) > 100000:
        raise ValueError("Deletion replay exceeds its bounded batch")
    count = 0
    for value in values:
        if set(value) != {"subject_kind", "subject_id", "reason"}:
            raise ValueError("Only content-free deletion records can be replayed")
        kind, subject, reason = value["subject_kind"], value["subject_id"], value["reason"]
        if kind not in {"listing", "post", "profile"} or reason not in {"expired", "takedown"} or len(subject) > 36:
            raise ValueError("Invalid deletion identity")
        ledger(db, kind, subject, reason)
        if kind == "listing" and db.get(Listing, subject):
            purge_listing(db, subject)
        elif kind == "post":
            versions = list(db.scalars(select(PostVersion.id).where(PostVersion.post_id == subject)))
            scrub_versions(db, versions, reason="takedown")
        elif kind == "profile":
            from .models import SourceAccount
            from .retention import remove_profile

            if db.get(SourceAccount, subject):
                remove_profile(db, subject)
        count += 1
    return count
