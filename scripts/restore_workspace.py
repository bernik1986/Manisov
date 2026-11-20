"""Verify and extract a rollback snapshot into a NEW directory (never overwrite live data)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def restore_workspace(backup: Path, destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Restore destination must not already exist")
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    with ZipFile(backup / "workspace.zip") as archive:
        if set(archive.namelist()) != set(manifest):
            raise ValueError("Archive contents do not match the manifest")
        for name, digest in manifest.items():
            path = (destination / name).resolve()
            if not path.is_relative_to(destination):
                raise ValueError("Unsafe archive path")
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        destination.mkdir(parents=True, exist_ok=False)
        for name in manifest:
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
    print(f"Verified and restored {len(manifest)} files to {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    restore_workspace(args.backup, args.destination)
