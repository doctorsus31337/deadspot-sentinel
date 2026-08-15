#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

REPOSITORY = "doctorsus31337/deadspot-sentinel"
EXCLUDED_PARTS = {
    ".git",
    ".qa-venv",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def project_version(root: Path) -> str:
    content = (root / "deadspot_sentinel" / "__init__.py").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r'^__version__\s*=\s*"([0-9]+(?:\.[0-9]+)*)"', content, re.MULTILINE
    )
    if not match:
        raise RuntimeError("Could not read the application version.")
    return match.group(1)


def included(path: Path, root: Path, output: Path) -> bool:
    relative = path.relative_to(root)
    output_inside_project = output == root or root in output.parents
    return (
        path.is_file()
        and not (output_inside_project and output in path.parents)
        and not EXCLUDED_PARTS.intersection(relative.parts)
        and path.suffix not in EXCLUDED_SUFFIXES
        and path.name != "update.json"
    )


def build(root: Path, output: Path, notes: str) -> tuple[Path, Path]:
    version = project_version(root)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"deadspot-sentinel-v{version}.zip"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(root.rglob("*")):
            if included(path, root, output):
                archive.write(path, Path("deadspot-sentinel") / path.relative_to(root))
    with zipfile.ZipFile(archive_path) as archive:
        packaged = set(archive.namelist())
    required = {
        "deadspot-sentinel/install.sh",
        "deadspot-sentinel/updater.sh",
        "deadspot-sentinel/run.py",
    }
    if not required.issubset(packaged):
        archive_path.unlink(missing_ok=True)
        raise RuntimeError("Release archive is missing required application files.")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest_path = output / "update.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": version,
                "download_url": (
                    f"https://github.com/{REPOSITORY}/releases/download/v{version}/"
                    f"deadspot-sentinel-v{version}.zip"
                ),
                "sha256": digest,
                "notes": notes,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return archive_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--notes",
        default="A verified DeadSpot Sentinel maintenance and feature release.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    archive, manifest = build(root, args.output_dir.resolve(), args.notes)
    print(archive)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
