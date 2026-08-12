#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
integration = importlib.import_module("deadspot_sentinel.system_integration")


class MemoryResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


def verify(archive_path: Path, manifest_path: Path, from_version: str) -> None:
    archive = archive_path.read_bytes()
    manifest = manifest_path.read_bytes()

    def opener(request, timeout):
        if request.full_url == integration.OFFICIAL_MANIFEST_URL:
            if timeout != 8:
                raise RuntimeError("Unexpected manifest timeout.")
            return MemoryResponse(manifest)
        if timeout != 30:
            raise RuntimeError("Unexpected archive timeout.")
        return MemoryResponse(archive)

    original_version = integration.__version__
    integration.__version__ = from_version
    try:
        info = integration.UpdateChecker(opener).check()
        if not info.available:
            raise RuntimeError(
                f"Release {info.latest_version} is not newer than {from_version}."
            )
        with tempfile.TemporaryDirectory() as directory:
            source = integration.UpdateInstaller(
                opener, Path(directory)
            ).prepare(info)
            required = source / "deadspot_sentinel" / "temperature.py"
            if not required.is_file():
                raise RuntimeError("Verified release is missing temperature.py.")
            packaged_version = source / "deadspot_sentinel" / "__init__.py"
            if f'__version__ = "{info.latest_version}"' not in packaged_version.read_text(
                encoding="utf-8"
            ):
                raise RuntimeError("Verified release contains the wrong version.")
    finally:
        integration.__version__ = original_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--from-version", required=True)
    args = parser.parse_args()
    verify(args.archive, args.manifest, args.from_version)
    raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    print(
        f"Verified updater path: {args.from_version} -> {raw['version']} "
        f"({args.archive.name})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
