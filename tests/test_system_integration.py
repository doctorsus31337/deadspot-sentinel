import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from deadspot_sentinel.system_integration import (
    AutostartManager,
    UpdateChecker,
    UpdateInfo,
    UpdateInstaller,
    version_tuple,
)


class AutostartTests(unittest.TestCase):
    def test_enable_and_disable_create_only_the_expected_desktop_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "autostart" / "deadspot-sentinel.desktop"
            manager = AutostartManager(path, Path("/opt/deadspot sentinel/run"))
            ok, _message = manager.set_enabled(True)
            self.assertTrue(ok)
            self.assertTrue(manager.enabled())
            content = path.read_text(encoding="utf-8")
            self.assertIn('Exec="/opt/deadspot sentinel/run"', content)
            ok, _message = manager.set_enabled(False)
            self.assertTrue(ok)
            self.assertFalse(manager.enabled())


class FakeResponse(io.BytesIO):
    def __init__(self, payload: dict[str, object] | bytes) -> None:
        super().__init__(
            payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


class UpdateCheckerTests(unittest.TestCase):
    def test_version_parser_handles_v_prefix(self):
        self.assertEqual(version_tuple("v1.2.3"), (1, 2, 3))

    def test_checker_reports_newer_https_release(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 8)
            self.assertEqual(request.full_url, "https://updates.example/manifest.json")
            return FakeResponse(
                {
                    "version": "99.0.0",
                    "download_url": "https://updates.example/releases/v99.0.0/deadspot-sentinel-v99.0.0.zip",
                    "sha256": "a" * 64,
                    "notes": "A future release",
                }
            )

        info = UpdateChecker(
            opener,
            manifest_url="https://updates.example/manifest.json",
            release_prefix="https://updates.example/releases/",
        ).check()
        self.assertTrue(info.available)
        self.assertEqual(info.latest_version, "99.0.0")

    def test_checker_rejects_non_https_manifest(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            UpdateChecker(manifest_url="http://updates.example/manifest.json").check()

    def test_checker_rejects_a_package_outside_the_locked_release_path(self):
        def opener(_request, timeout):
            self.assertEqual(timeout, 8)
            return FakeResponse(
                {
                    "version": "99.0.0",
                    "download_url": "https://example.org/evil.zip",
                    "sha256": "b" * 64,
                }
            )

        with self.assertRaisesRegex(ValueError, "official versioned release"):
            UpdateChecker(opener).check()


class UpdateInstallerTests(unittest.TestCase):
    @staticmethod
    def _archive(extra_name: str | None = None) -> bytes:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            for name in UpdateInstaller.REQUIRED_FILES:
                archive.writestr(name, "placeholder")
            if extra_name:
                archive.writestr(extra_name, "unsafe")
        return payload.getvalue()

    @staticmethod
    def _info(payload: bytes) -> UpdateInfo:
        version = "99.0.0"
        return UpdateInfo(
            True,
            "0.4.0",
            version,
            "https://github.com/doctorsus31337/deadspot-sentinel/"
            f"releases/download/v{version}/deadspot-sentinel-v{version}.zip",
            hashlib.sha256(payload).hexdigest(),
            "test",
        )

    def test_prepare_verifies_and_extracts_an_official_archive(self):
        payload = self._archive()

        def opener(_request, timeout):
            self.assertEqual(timeout, 30)
            return FakeResponse(payload)

        with tempfile.TemporaryDirectory() as directory:
            source = UpdateInstaller(opener, Path(directory)).prepare(
                self._info(payload)
            )
            self.assertTrue((source / "install.sh").is_file())
            self.assertTrue((source / "updater.sh").is_file())

    def test_prepare_rejects_checksum_mismatch(self):
        payload = self._archive()
        info = self._info(payload)
        bad_info = UpdateInfo(
            info.available,
            info.current_version,
            info.latest_version,
            info.download_url,
            "0" * 64,
            info.notes,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "SHA-256"),
        ):
            UpdateInstaller(
                lambda *_args, **_kwargs: FakeResponse(payload), Path(directory)
            ).prepare(bad_info)

    def test_prepare_rejects_path_traversal(self):
        payload = self._archive("deadspot-sentinel/../escape")
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "unsafe path"),
        ):
            UpdateInstaller(
                lambda *_args, **_kwargs: FakeResponse(payload), Path(directory)
            ).prepare(self._info(payload))


if __name__ == "__main__":
    unittest.main()
