from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from . import __version__

OFFICIAL_REPOSITORY = "doctorsus31337/deadspot-sentinel"
OFFICIAL_MANIFEST_URL = (
    "https://github.com/doctorsus31337/deadspot-sentinel/"
    "releases/latest/download/update.json"
)
OFFICIAL_RELEASE_PREFIX = (
    "https://github.com/doctorsus31337/deadspot-sentinel/releases/download/"
)


def autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "deadspot-sentinel.desktop"


def default_launcher() -> Path:
    installed = Path.home() / ".local" / "bin" / "deadspot-sentinel"
    return installed if installed.exists() else Path(sys.argv[0]).resolve()


def default_icon() -> str:
    installed = (
        Path.home()
        / ".local"
        / "share"
        / "deadspot-sentinel"
        / "assets"
        / "deadspot-sentinel.svg"
    )
    return str(installed) if installed.exists() else "network-wireless"


def desktop_exec_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class AutostartManager:
    def __init__(self, path: Path | None = None, launcher: Path | None = None) -> None:
        self.path = path or autostart_path()
        self.launcher = launcher or default_launcher()

    def enabled(self) -> bool:
        return self.path.exists()

    def set_enabled(self, enabled: bool) -> tuple[bool, str]:
        try:
            if not enabled:
                self.path.unlink(missing_ok=True)
                return True, "DeadSpot Sentinel will no longer open automatically."
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "\n".join(
                    (
                        "[Desktop Entry]",
                        "Type=Application",
                        "Name=DeadSpot Sentinel",
                        "Comment=Fast dual-Wi-Fi connectivity monitor",
                        f"Exec={desktop_exec_quote(str(self.launcher))}",
                        f"Icon={default_icon()}",
                        "Terminal=false",
                        "X-GNOME-Autostart-enabled=true",
                        "",
                    )
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            return False, str(exc)
        return True, "DeadSpot Sentinel will open automatically when XFCE starts."


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    available: bool
    current_version: str
    latest_version: str
    download_url: str
    sha256: str
    notes: str


def version_tuple(version: str) -> tuple[int, ...]:
    match = re.match(r"^v?(\d+(?:\.\d+)*)", version.strip())
    if not match:
        raise ValueError(f"Invalid version: {version}")
    return tuple(int(part) for part in match.group(1).split("."))


class UpdateChecker:
    MAX_MANIFEST_BYTES = 65_536

    def __init__(
        self,
        opener=urllib.request.urlopen,
        manifest_url: str = OFFICIAL_MANIFEST_URL,
        release_prefix: str = OFFICIAL_RELEASE_PREFIX,
    ) -> None:
        self.opener = opener
        self.manifest_url = manifest_url
        self.release_prefix = release_prefix

    def check(self) -> UpdateInfo:
        parsed = urlparse(self.manifest_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("The update manifest must use a valid HTTPS URL.")
        request = urllib.request.Request(
            self.manifest_url,
            headers={"User-Agent": f"DeadSpot-Sentinel/{__version__}"},
        )
        with self.opener(request, timeout=8) as response:
            payload = response.read(self.MAX_MANIFEST_BYTES + 1)
        if len(payload) > self.MAX_MANIFEST_BYTES:
            raise ValueError("The update manifest is unexpectedly large.")
        raw = json.loads(payload.decode("utf-8"))
        latest = str(raw["version"])
        download_url = str(raw.get("download_url", ""))
        expected_url = (
            f"{self.release_prefix}v{latest}/deadspot-sentinel-v{latest}.zip"
        )
        if download_url != expected_url:
            raise ValueError("The update package is not an official versioned release asset.")
        digest = str(raw.get("sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("The update manifest does not contain a valid SHA-256 digest.")
        return UpdateInfo(
            version_tuple(latest) > version_tuple(__version__),
            __version__,
            latest,
            download_url,
            digest,
            str(raw.get("notes", "")),
        )


class UpdateInstaller:
    MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
    MAX_EXTRACTED_BYTES = 75 * 1024 * 1024
    REQUIRED_FILES: ClassVar[set[str]] = {
        "deadspot-sentinel/install.sh",
        "deadspot-sentinel/launcher.sh",
        "deadspot-sentinel/updater.sh",
        "deadspot-sentinel/run.py",
    }

    def __init__(self, opener=urllib.request.urlopen, staging_dir: Path | None = None) -> None:
        self.opener = opener
        self.staging_dir = staging_dir

    @staticmethod
    def _validate_release_url(info: UpdateInfo) -> None:
        expected = (
            f"{OFFICIAL_RELEASE_PREFIX}v{info.latest_version}/"
            f"deadspot-sentinel-v{info.latest_version}.zip"
        )
        if info.download_url != expected:
            raise ValueError("Refusing a package outside the official GitHub release.")

    def prepare(self, info: UpdateInfo) -> Path:
        self._validate_release_url(info)
        staging_parent = self.staging_dir
        if staging_parent is not None:
            staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix="deadspot-update-", dir=staging_parent)
        )
        archive_path = staging / "update.zip"
        digest = hashlib.sha256()
        size = 0
        request = urllib.request.Request(
            info.download_url,
            headers={"User-Agent": f"DeadSpot-Sentinel/{__version__}"},
        )
        try:
            with self.opener(request, timeout=30) as response, archive_path.open(
                "wb"
            ) as stream:
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > self.MAX_ARCHIVE_BYTES:
                        raise ValueError("The update archive is unexpectedly large.")
                    digest.update(chunk)
                    stream.write(chunk)
            if not size:
                raise ValueError("The update download was empty.")
            if not re.fullmatch(r"[0-9a-f]{64}", info.sha256.lower()):
                raise ValueError("The update digest is invalid.")
            if digest.hexdigest() != info.sha256.lower():
                raise ValueError("The downloaded update failed SHA-256 verification.")
            destination = staging / "extracted"
            self._extract_verified_archive(archive_path, destination)
            return destination / "deadspot-sentinel"
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _extract_verified_archive(self, archive_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            files = set()
            total = 0
            for member in archive.infolist():
                pure = Path(member.filename)
                parts = pure.parts
                if (
                    not parts
                    or parts[0] != "deadspot-sentinel"
                    or pure.is_absolute()
                    or ".." in parts
                ):
                    raise ValueError("The update archive contains an unsafe path.")
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("The update archive contains an unsupported symlink.")
                total += member.file_size
                if total > self.MAX_EXTRACTED_BYTES:
                    raise ValueError("The expanded update is unexpectedly large.")
                if not member.is_dir():
                    files.add(member.filename.rstrip("/"))
            if not self.REQUIRED_FILES.issubset(files):
                raise ValueError("The update archive is missing required application files.")
            archive.extractall(destination)

    @staticmethod
    def launch(prepared_source: Path, current_pid: int | None = None) -> None:
        updater = prepared_source / "updater.sh"
        if not updater.is_file():
            raise ValueError("The verified update does not contain its installer helper.")
        log_dir = Path.home() / ".local" / "state" / "deadspot-sentinel"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = (log_dir / "update-launch.log").open("ab")
        try:
            subprocess.Popen(
                [
                    "/usr/bin/env",
                    "bash",
                    str(updater),
                    str(prepared_source),
                    str(current_pid or os.getpid()),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            log.close()
