"""Local Docker backup; production Storage exports are a separate operation."""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
folder = args.directory.resolve()
folder.mkdir(parents=True, exist_ok=True)
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
        "tar",
        "-cf",
        "-",
        "-C",
        "/app/.data",
        "media",
    ],
}
root = Path(__file__).resolve().parents[1]
for name, command in commands.items():
    with (folder / name).open("xb") as stream:
        subprocess.run(command, cwd=root, stdout=stream, check=True)
    print(name)
print(
    "Backups created. Validate a separate restore and replay deletions before claiming recovery."
)
