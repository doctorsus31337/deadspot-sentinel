from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import (
    QLockFile,
    QObject,
    QProcess,
    QRunnable,
    QStandardPaths,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon

from . import __version__
from .config import AppConfig, OutageLog, state_dir
from .network import (
    AdapterHealth,
    HealthState,
    NetworkInspector,
    NetworkSnapshot,
    RecoveryManager,
    SpeedSample,
    ThroughputSampler,
)
from .system_integration import (
    AutostartManager,
    UpdateChecker,
    UpdateInfo,
    UpdateInstaller,
)
from .temperature import (
    TemperatureLevel,
    TemperatureReader,
    TemperatureReading,
    next_temperature_level,
)
from .ui import (
    COLORS,
    AlertPopup,
    SettingsDialog,
    StatusWindow,
    TrayController,
    activate_theme,
    app_style,
    show_about_dialog,
    status_icon,
)


class SnapshotSignals(QObject):
    completed = pyqtSignal(object)


class SnapshotWorker(QRunnable):
    def __init__(self, inspector: NetworkInspector) -> None:
        super().__init__()
        self.inspector = inspector
        self.signals = SnapshotSignals()

    def run(self) -> None:
        self.signals.completed.emit(self.inspector.collect())


class ActionSignals(QObject):
    completed = pyqtSignal(bool, str)


class ActionWorker(QRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = ActionSignals()

    def run(self) -> None:
        try:
            ok, message = self.operation()
        except Exception as exc:
            ok, message = False, str(exc)
        self.signals.completed.emit(ok, message)


class SpeedSignals(QObject):
    completed = pyqtSignal(object)


class SpeedWorker(QRunnable):
    def __init__(
        self,
        sampler: ThroughputSampler,
        adapter: AdapterHealth,
        sample_bytes: int,
    ) -> None:
        super().__init__()
        self.sampler = sampler
        self.adapter = adapter
        self.sample_bytes = sample_bytes
        self.signals = SpeedSignals()

    def run(self) -> None:
        self.signals.completed.emit(
            self.sampler.measure(
                self.adapter.device.name,
                self.adapter.device.connection,
                self.sample_bytes,
            )
        )


class TemperatureSignals(QObject):
    completed = pyqtSignal(object)


class TemperatureWorker(QRunnable):
    def __init__(self, reader: TemperatureReader) -> None:
        super().__init__()
        self.reader = reader
        self.signals = TemperatureSignals()

    def run(self) -> None:
        self.signals.completed.emit(self.reader.read())


class UpdateSignals(QObject):
    completed = pyqtSignal(object, str)


class InstallSignals(QObject):
    completed = pyqtSignal(object, str)
    progress = pyqtSignal(str, int)


class UpdateWorker(QRunnable):
    def __init__(self, checker: UpdateChecker) -> None:
        super().__init__()
        self.checker = checker
        self.signals = UpdateSignals()

    def run(self) -> None:
        try:
            self.signals.completed.emit(self.checker.check(), "")
        except Exception as exc:
            self.signals.completed.emit(None, str(exc))


class InstallWorker(QRunnable):
    def __init__(self, installer: UpdateInstaller, info: UpdateInfo) -> None:
        super().__init__()
        self.installer = installer
        self.info = info
        self.signals = InstallSignals()

    def run(self) -> None:
        try:
            self.signals.completed.emit(
                self.installer.prepare(self.info, self.signals.progress.emit), ""
            )
        except Exception as exc:
            self.signals.completed.emit(None, str(exc))


class SentinelApp(QObject):
    def __init__(self, qt_app: QApplication, config: AppConfig) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.config = config
        self.outages = OutageLog()
        self.autostart = AutostartManager()
        self.update_checker = UpdateChecker()
        self.update_installer = UpdateInstaller()
        self.inspector = NetworkInspector()
        self.recovery = RecoveryManager()
        self.speed_sampler = ThroughputSampler()
        self.temperature_reader = TemperatureReader()
        self.pool = QThreadPool.globalInstance()
        self.window = StatusWindow(
            self.config.automatic_failover,
            self.config.speed_sample_interval_minutes,
            self.autostart.enabled(),
            self.config.auto_install_updates,
        )
        self.popup = AlertPopup()
        self.tray = TrayController(self.window)
        self.timer = QTimer(self)
        self.timer.setInterval(self.config.check_interval_ms)
        self.timer.timeout.connect(self.request_check)
        self.temperature_timer = QTimer(self)
        self.temperature_timer.setInterval(
            max(2, self.config.temperature_poll_seconds) * 1000
        )
        self.temperature_timer.timeout.connect(self.request_temperature)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(6 * 60 * 60 * 1000)
        self.update_timer.timeout.connect(lambda: self.check_updates(manual=False))
        self.busy = False
        self.speed_busy = False
        self.temperature_busy = False
        self.update_busy = False
        self.last_snapshot: NetworkSnapshot | None = None
        self.had_online_state = False
        self.was_online: bool | None = None
        self.outage_started: float | None = None
        self.failure_counts: dict[str, int] = {}
        self.last_failover_at = 0.0
        self.speed_samples: dict[str, SpeedSample] = {}
        self.speed_active_key = ""
        self.speed_active_stable_checks = 0
        self.temperature_level = TemperatureLevel.UNAVAILABLE

        self.window.reconnect_requested.connect(self.reconnect)
        self.window.prefer_requested.connect(self.prefer)
        self.window.auto_failover_changed.connect(self.set_auto_failover)
        self.window.check_requested.connect(self.request_check)
        self.window.speed_test_requested.connect(self.request_speed_test)
        self.window.speed_interval_changed.connect(self.set_speed_interval)
        self.window.open_log_requested.connect(self.open_activity_log)
        self.window.open_diagnostic_log_requested.connect(self.open_diagnostic_log)
        self.window.settings_requested.connect(self.open_settings)
        self.window.about_requested.connect(
            lambda: show_about_dialog(self.window, __version__)
        )
        self.window.update_check_requested.connect(self.check_updates)
        self.window.exit_requested.connect(self.quit)
        self.window.autostart_changed.connect(self.set_autostart)
        self.window.auto_update_changed.connect(self.set_auto_update_checks)
        self.window.temperature_alert_test_requested.connect(
            self.test_temperature_alert
        )
        self.tray.open_action.triggered.connect(self.show_window)
        self.tray.check_action.triggered.connect(self.request_check)
        self.tray.speed_action.triggered.connect(self.request_speed_test)
        self.tray.quit_action.triggered.connect(self.quit)

    def start(self) -> None:
        self.tray.tray.show()
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QTimer.singleShot(1000, lambda: self._wait_for_system_tray(1))
        self.request_check()
        self.request_temperature()
        self.timer.start()
        self.temperature_timer.start()
        self._sync_update_timer()
        if self.config.auto_update_checks or self.config.auto_install_updates:
            QTimer.singleShot(5000, lambda: self.check_updates(manual=False))

    def _wait_for_system_tray(self, attempt: int) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            return
        if attempt < 15:
            QTimer.singleShot(
                1000, lambda next_attempt=attempt + 1: self._wait_for_system_tray(next_attempt)
            )
            return
        self.outages.append(
            {
                "event": "system_tray_unavailable",
                "at": datetime.now(UTC).isoformat(),
                "waited_seconds": attempt,
            }
        )
        self.window.show()
        self.window.raise_()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def request_check(self) -> None:
        if self.busy:
            return
        self.busy = True
        worker = SnapshotWorker(self.inspector)
        worker.signals.completed.connect(self._snapshot_ready)
        self.pool.start(worker)

    def _snapshot_ready(self, snapshot: NetworkSnapshot) -> None:
        self.busy = False
        previous = self.last_snapshot
        self.last_snapshot = snapshot
        self.window.update_snapshot(snapshot, self.speed_samples)
        self.tray.update_snapshot(
            snapshot, self.reconnect, self.prefer, self.speed_samples
        )
        self._track_adapter_failures(snapshot)
        self._track_global_state(snapshot)
        self._consider_failover(snapshot, previous)
        self._maybe_schedule_speed_sample(snapshot)

    @staticmethod
    def _speed_key(adapter: AdapterHealth) -> str:
        return f"{adapter.device.name}\0{adapter.device.connection}"

    def _active_online_adapter(self) -> AdapterHealth | None:
        if not self.last_snapshot:
            return None
        active = self.last_snapshot.default_adapter
        if active and active.health is HealthState.ONLINE:
            return active
        return None

    def _maybe_schedule_speed_sample(self, snapshot: NetworkSnapshot) -> None:
        interval = self.config.speed_sample_interval_minutes
        if interval <= 0:
            self.window.speed_panel.set_schedule("Automatic sampling is off.")
            return
        active = snapshot.default_adapter
        if not active or active.health is not HealthState.ONLINE:
            self.speed_active_key = ""
            self.speed_active_stable_checks = 0
            self.window.speed_panel.set_schedule("Waiting for a stable active route.")
            return
        key = self._speed_key(active)
        if key != self.speed_active_key:
            self.speed_active_key = key
            self.speed_active_stable_checks = 1
        else:
            self.speed_active_stable_checks += 1
        if self.speed_busy:
            self.window.speed_panel.set_schedule("Sample in progress…")
            return
        previous = self.speed_samples.get(key)
        if previous is None and self.speed_active_stable_checks >= 2:
            self.request_speed_test(automatic=True)
            return
        if previous is None:
            self.window.speed_panel.set_schedule(
                "First sample starts after one more healthy check."
            )
            return
        remaining = interval * 60 - (time.time() - previous.timestamp)
        if remaining <= 0:
            self.request_speed_test(automatic=True)
            return
        if remaining >= 120:
            text = f"Next sample in {remaining / 60:.0f} minutes."
        else:
            text = f"Next sample in {max(1, int(remaining))} seconds."
        self.window.speed_panel.set_schedule(text)

    def request_speed_test(self, automatic: bool = False) -> None:
        if self.speed_busy:
            return
        active = self._active_online_adapter()
        if not active:
            if not automatic:
                self.popup.show_alert(
                    "Speed sample unavailable",
                    "The active/default Wi-Fi route must be online before a speed sample can run.",
                    COLORS["amber"],
                    "Open status",
                    self.show_window,
                )
            return
        self.speed_busy = True
        self.window.speed_panel.set_running(True, active.device.name)
        worker = SpeedWorker(
            self.speed_sampler,
            active,
            self.config.speed_sample_bytes,
        )
        worker.signals.completed.connect(self._speed_sample_ready)
        self.pool.start(worker)

    def _speed_sample_ready(self, sample: SpeedSample) -> None:
        self.speed_busy = False
        key = f"{sample.device}\0{sample.connection}"
        self.speed_samples[key] = sample
        self.window.speed_panel.update_sample(sample)
        if self.last_snapshot:
            self.window.update_snapshot(self.last_snapshot, self.speed_samples)
            self.tray.update_snapshot(
                self.last_snapshot,
                self.reconnect,
                self.prefer,
                self.speed_samples,
            )
        event: dict[str, object] = {
            "event": "speed_sample",
            "at": datetime.now(UTC).isoformat(),
            "device": sample.device,
            "connection": sample.connection,
            "success": sample.success,
            "bytes_downloaded": sample.bytes_downloaded,
        }
        if sample.mbps is not None:
            event["download_mbps"] = round(sample.mbps, 2)
        else:
            event["detail"] = sample.detail
        self.outages.append(event)
        if self.last_snapshot:
            self._maybe_schedule_speed_sample(self.last_snapshot)

    def request_temperature(self) -> None:
        if self.temperature_busy:
            return
        self.temperature_busy = True
        worker = TemperatureWorker(self.temperature_reader)
        worker.signals.completed.connect(self._temperature_ready)
        self.pool.start(worker)

    def test_temperature_alert(self) -> None:
        self.popup.show_alert(
            "HIGH TEMP — COOL ASAP (TEST)",
            "This is a simulated temperature warning. Your CPU did not cross a heat threshold.",
            COLORS["amber"],
            "Open status",
            self.show_window,
        )

    def _temperature_ready(self, reading: TemperatureReading) -> None:
        self.temperature_busy = False
        previous = self.temperature_level
        current = next_temperature_level(
            reading.celsius,
            previous,
            self.config.temperature_warning_c,
            self.config.temperature_critical_c,
        )
        self.temperature_level = current
        self.window.temperature_panel.update_reading(reading, current)
        self.tray.update_temperature(reading, current)
        if not self.config.temperature_alerts_enabled or reading.celsius is None:
            return
        ranks = {
            TemperatureLevel.UNAVAILABLE: 0,
            TemperatureLevel.NORMAL: 0,
            TemperatureLevel.HIGH: 1,
            TemperatureLevel.CRITICAL: 2,
        }
        if ranks[current] > ranks[previous]:
            if current is TemperatureLevel.CRITICAL:
                title = "CRITICAL TEMP — COOL IMMEDIATELY"
                body = (
                    f"CPU temperature reached {reading.celsius:.1f} °C. Pause heavy workloads, "
                    "improve airflow, and check that the cooling vents are unobstructed."
                )
                color = COLORS["red"]
            else:
                title = "HIGH TEMP — COOL ASAP"
                body = (
                    f"CPU temperature reached {reading.celsius:.1f} °C. Consider reducing the workload "
                    "and giving the laptop more airflow."
                )
                color = COLORS["amber"]
            self.popup.show_alert(title, body, color, "Open status", self.show_window)
            self.outages.append(
                {
                    "event": "temperature_alert",
                    "at": datetime.now(UTC).isoformat(),
                    "level": current.value,
                    "celsius": reading.celsius,
                    "source": reading.source,
                }
            )
        elif (
            current is TemperatureLevel.NORMAL
            and previous in {TemperatureLevel.HIGH, TemperatureLevel.CRITICAL}
        ):
            self.popup.show_alert(
                "CPU temperature stabilized",
                f"CPU temperature returned to {reading.celsius:.1f} °C.",
                COLORS["green"],
            )
            QTimer.singleShot(7000, self.popup.hide)
            self.outages.append(
                {
                    "event": "temperature_recovered",
                    "at": datetime.now(UTC).isoformat(),
                    "celsius": reading.celsius,
                    "source": reading.source,
                }
            )

    def set_speed_interval(self, minutes: int) -> None:
        self.config.speed_sample_interval_minutes = max(0, int(minutes))
        self.config.save()
        if self.last_snapshot:
            self._maybe_schedule_speed_sample(self.last_snapshot)

    def open_activity_log(self) -> None:
        self._open_log_file(self.outages.path, "Activity Log")

    def open_diagnostic_log(self) -> None:
        self._open_log_file(state_dir() / "application.log", "Diagnostic Log")

    def _open_log_file(self, path: Path, title: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self.window, title, str(exc))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.information(
                self.window,
                title,
                f"The log is stored at:\n{path}",
            )

    def set_autostart(self, enabled: bool) -> None:
        ok, message = self.autostart.set_enabled(enabled)
        actual = self.autostart.enabled()
        self.window.set_autostart_state(actual)
        if not ok:
            self.popup.show_alert("Startup setting failed", message, COLORS["red"])

    def set_auto_update_checks(self, enabled: bool) -> None:
        self.config.auto_install_updates = enabled
        self.config.auto_update_checks = enabled or self.config.auto_update_checks
        self.config.save()
        self.window.set_auto_update_state(enabled)
        self._sync_update_timer()
        if enabled:
            self.check_updates(manual=False)

    def _sync_update_timer(self) -> None:
        if self.config.auto_update_checks or self.config.auto_install_updates:
            self.update_timer.start()
        else:
            self.update_timer.stop()

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.window,
            theme=self.config.theme,
            autostart_enabled=self.autostart.enabled(),
            notify_when_restored=self.config.notify_when_restored,
            speed_interval_minutes=self.config.speed_sample_interval_minutes,
            temperature_alerts_enabled=self.config.temperature_alerts_enabled,
            temperature_warning_c=self.config.temperature_warning_c,
            temperature_critical_c=self.config.temperature_critical_c,
            auto_update_checks=self.config.auto_update_checks,
            auto_install_updates=self.config.auto_install_updates,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        selected_theme = str(values["theme"])
        theme_changed = selected_theme != self.config.theme
        self.set_autostart(bool(values["autostart_enabled"]))
        self.config.theme = selected_theme
        self.config.notify_when_restored = bool(values["notify_when_restored"])
        self.config.speed_sample_interval_minutes = int(
            values["speed_interval_minutes"]
        )
        self.config.temperature_alerts_enabled = bool(
            values["temperature_alerts_enabled"]
        )
        self.config.temperature_warning_c = max(
            60, min(100, int(values["temperature_warning_c"]))
        )
        self.config.temperature_critical_c = max(
            self.config.temperature_warning_c + 1,
            min(110, int(values["temperature_critical_c"])),
        )
        self.config.auto_update_checks = bool(values["auto_update_checks"])
        self.config.auto_install_updates = bool(values["auto_install_updates"])
        if self.config.auto_install_updates:
            self.config.auto_update_checks = True
        self.config.save()
        self.window.set_auto_update_state(self.config.auto_install_updates)
        self._sync_update_timer()
        interval_box = self.window.speed_panel.interval
        interval_box.blockSignals(True)
        selected = interval_box.findData(self.config.speed_sample_interval_minutes)
        if selected >= 0:
            interval_box.setCurrentIndex(selected)
        interval_box.blockSignals(False)
        if self.last_snapshot:
            self._maybe_schedule_speed_sample(self.last_snapshot)
        self.request_temperature()
        if theme_changed:
            QTimer.singleShot(150, self.restart)
        elif self.config.auto_update_checks or self.config.auto_install_updates:
            self.check_updates(manual=False)

    def check_updates(self, manual: bool = True) -> None:
        if self.update_busy:
            return
        self.update_busy = True
        worker = UpdateWorker(self.update_checker)

        def completed(info: UpdateInfo | None, error: str) -> None:
            self.update_busy = False
            self.config.last_update_check_timestamp = time.time()
            self.config.save()
            if error:
                if manual:
                    QMessageBox.warning(self.window, "Update Check Failed", error)
                return
            assert info is not None
            if info.available:
                if self.config.auto_install_updates:
                    self.install_update(info)
                    return
                answer = QMessageBox.question(
                    self.window,
                    "Verified Update Available",
                    f"DeadSpot Sentinel {info.latest_version} is available.\n\n"
                    f"{info.notes or 'No release notes were provided.'}\n\n"
                    "Download, verify, install, and restart now?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.install_update(info)
            elif manual:
                QMessageBox.information(
                    self.window,
                    "DeadSpot Sentinel Is Current",
                    f"You are running the latest published version ({info.current_version}).",
                )

        worker.signals.completed.connect(completed)
        self.pool.start(worker)

    def install_update(self, info: UpdateInfo) -> None:
        if self.update_busy:
            return
        self.update_busy = True
        self.popup.show_progress_alert(
            "Downloading verified update",
            f"DeadSpot Sentinel {info.latest_version} is being downloaded and checked.",
            COLORS["accent"],
        )
        worker = InstallWorker(self.update_installer, info)
        worker.signals.progress.connect(self.popup.update_progress)

        def completed(prepared_source: Path | None, error: str) -> None:
            self.update_busy = False
            if error:
                self.popup.show_alert(
                    "Update verification failed",
                    error,
                    COLORS["red"],
                    "Open status",
                    self.show_window,
                )
                return
            assert prepared_source is not None
            try:
                self.update_installer.launch(prepared_source)
            except Exception as exc:
                self.popup.show_alert(
                    "Update launch failed",
                    str(exc),
                    COLORS["red"],
                    "Open status",
                    self.show_window,
                )
                return
            self.timer.stop()
            self.tray.tray.hide()
            self.qt_app.quit()

        worker.signals.completed.connect(completed)
        self.pool.start(worker)

    def restart(self) -> None:
        script = str(Path(sys.argv[0]).resolve())
        started = QProcess.startDetached(
            sys.executable,
            [script, *sys.argv[1:]],
            str(Path(script).parent),
        )
        succeeded = started[0] if isinstance(started, tuple) else bool(started)
        if not succeeded:
            QMessageBox.warning(
                self.window,
                "Restart Failed",
                "The new theme was saved, but DeadSpot Sentinel could not restart automatically. "
                "Please exit and reopen it.",
            )
            return
        self.quit()

    def _track_adapter_failures(self, snapshot: NetworkSnapshot) -> None:
        present = {item.device.name for item in snapshot.adapters}
        self.failure_counts = {
            name: count
            for name, count in self.failure_counts.items()
            if name in present
        }
        for item in snapshot.adapters:
            if item.health is HealthState.OFFLINE:
                self.failure_counts[item.device.name] = (
                    self.failure_counts.get(item.device.name, 0) + 1
                )
            else:
                self.failure_counts[item.device.name] = 0

    def _track_global_state(self, snapshot: NetworkSnapshot) -> None:
        if snapshot.collection_error:
            return
        online = snapshot.system_online
        now = time.time()
        if self.was_online is None:
            self.was_online = online
            self.had_online_state = online
            return
        if self.was_online and not online:
            self.outage_started = now
            self.outages.append(
                {
                    "event": "offline",
                    "at": datetime.now(UTC).isoformat(),
                    "adapters": [item.device.name for item in snapshot.adapters],
                }
            )
            if not snapshot.standby_only:
                self.popup.show_alert(
                    "Internet connection lost",
                    "Both Wi-Fi paths failed their connectivity checks. DeadSpot Sentinel will keep checking automatically.",
                    COLORS["red"],
                    "Open status",
                    self.show_window,
                )
        elif not self.was_online and online:
            duration = now - self.outage_started if self.outage_started else 0.0
            self.outages.append(
                {
                    "event": "online",
                    "at": datetime.now(UTC).isoformat(),
                    "outage_seconds": round(duration, 2),
                    "default_device": snapshot.default_device,
                }
            )
            if self.config.notify_when_restored:
                self.popup.show_alert(
                    "Internet connection restored",
                    f"You are back online via {snapshot.default_device or 'Wi-Fi'}. Outage duration: {duration:.1f} seconds.",
                    COLORS["green"],
                )
                QTimer.singleShot(7000, self.popup.hide)
            self.outage_started = None
            self.had_online_state = True
        self.was_online = online

    def _consider_failover(
        self, snapshot: NetworkSnapshot, previous: NetworkSnapshot | None
    ) -> None:
        active = snapshot.default_adapter
        backup = snapshot.best_online_backup
        if not active or active.health is not HealthState.OFFLINE or not backup:
            return
        failures = self.failure_counts.get(active.device.name, 0)
        if failures == 1 and self.config.popup_on_primary_failure:
            self.popup.show_alert(
                "Primary internet path failed",
                f"{active.device.name} is not reaching the internet, but {backup.device.name} is online.",
                COLORS["amber"],
                f"Use {backup.device.name}",
                lambda: self.prefer(backup.device.name),
            )
        if not self.config.automatic_failover:
            return
        if failures < self.config.failover_failure_threshold:
            return
        if (
            time.monotonic() - self.last_failover_at
            < self.config.failover_cooldown_seconds
        ):
            return
        self.last_failover_at = time.monotonic()
        self.prefer(backup.device.name, automatic=True)

    def set_auto_failover(self, enabled: bool) -> None:
        if enabled:
            answer = QMessageBox.question(
                self.window,
                "Enable automatic failover?",
                "When the active Wi-Fi path fails twice and another adapter is online, DeadSpot Sentinel will "
                "change the saved NetworkManager route metrics to promote the working adapter. It will not "
                "automatically switch back. Enable this feature?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.window.auto_failover.blockSignals(True)
                self.window.auto_failover.setChecked(False)
                self.window.auto_failover.blockSignals(False)
                return
        self.config.automatic_failover = enabled
        self.config.save()

    def _find_adapter(self, device: str) -> AdapterHealth | None:
        if not self.last_snapshot:
            return None
        return next(
            (
                item
                for item in self.last_snapshot.adapters
                if item.device.name == device
            ),
            None,
        )

    def reconnect(self, device: str, connection: str) -> None:
        self._run_action(lambda: self.recovery.reconnect(device, connection))

    def prefer(self, device: str, automatic: bool = False) -> None:
        snapshot = self.last_snapshot
        target = self._find_adapter(device)
        if not snapshot or not target:
            return
        if not automatic:
            answer = QMessageBox.question(
                self.window,
                f"Prefer {device}?",
                f"This will make {device} the primary route by updating the saved route metrics for your "
                "currently connected Wi-Fi profiles. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._run_action(
            lambda: self.recovery.prefer(target, snapshot.adapters), automatic=automatic
        )

    def _run_action(self, operation, automatic: bool = False) -> None:
        worker = ActionWorker(operation)

        def completed(ok: bool, message: str) -> None:
            if ok:
                self.popup.show_alert(
                    "Network action completed", message, COLORS["green"]
                )
                QTimer.singleShot(6000, self.popup.hide)
            else:
                self.popup.show_alert(
                    "Network action failed",
                    message,
                    COLORS["red"],
                    "Open status",
                    self.show_window,
                )
            self.request_check()

        worker.signals.completed.connect(completed)
        self.pool.start(worker)

    def quit(self) -> None:
        self.timer.stop()
        self.temperature_timer.stop()
        self.update_timer.stop()
        self.tray.tray.hide()
        self.qt_app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DeadSpot Sentinel")
    lock_directory = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    )
    lock_directory.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(lock_directory / "instance.lock"))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(
            None,
            "DeadSpot Sentinel",
            "DeadSpot Sentinel is already running in the system tray.",
        )
        return 0
    config = AppConfig.load()
    config.theme = activate_theme(config.theme)
    app.setWindowIcon(status_icon(COLORS["accent"]))
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(app_style())
    sentinel = SentinelApp(app, config)
    sentinel.start()
    app._deadspot_sentinel = sentinel  # keep the controller alive for the Qt event loop
    app._deadspot_instance_lock = instance_lock
    return app.exec()
