"""Local Docker DB plus retained managed media, deletion ledger and checksums."""

import argparse
import subprocess
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
folder = args.directory.resolve()
root = Path(__file__).resolve().parents[1]
if folder.is_relative_to(root) and not folder.is_relative_to(root / ".data"):
    raise SystemExit("Keep backups under ignored .data or outside the public repository.")
folder.mkdir(parents=True, exist_ok=True)
probe = subprocess.run(["docker", "compose", "exec", "-T", "api", "/app/apps/api/.venv/bin/python", "-c",
    "from bouquetbrowse.config import get_settings; from sqlalchemy.engine import make_url; u=make_url(get_settings().database_url); print(u.host == 'db' and u.database == 'bouquetbrowse')"],
    cwd=root, capture_output=True, text=True, check=True)
if probe.stdout.strip() != "True":
    raise SystemExit("API uses a different database. Export that managed database separately; this local Docker dump would not match its media/deletion ledger.")
stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
commands = {
    f"database-{stamp}.dump": [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "pg_dump",
        "-U",
        "bouquet",
        "-d",
        "bouquetbrowse",
        "-Fc",
    ],
    f"media-{stamp}.tar": [
        "docker",
        "compose",
        "exec",
        "-T",
        "api",
        "/app/apps/api/.venv/bin/python", "-m", "bouquetbrowse.cli", "backup-media",
    ],
    f"deletions-{stamp}.jsonl": ["docker", "compose", "exec", "-T", "api", "/app/apps/api/.venv/bin/python", "-m", "bouquetbrowse.cli", "deletion-export"],
}
files = []
for name, command in commands.items():
    with (folder / name).open("xb") as stream:
        subprocess.run(command, cwd=root, stdout=stream, check=True)
    print(name)
    hasher = hashlib.sha256()
    with (folder / name).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    files.append({"name": name, "sha256": hasher.hexdigest(), "bytes": (folder / name).stat().st_size})
manifest = {"version": "bouquet-backup-v1", "created_at": stamp, "files": files,
            "note": "Database and managed media exported separately. Retain newer deletion ledgers separately and replay after restore."}
(folder / f"manifest-{stamp}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(
    "Backups created. Validate a separate restore and replay deletions before claiming recovery."
)
