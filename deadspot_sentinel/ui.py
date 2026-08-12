from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .network import AdapterHealth, HealthState, NetworkSnapshot, SpeedSample
from .temperature import TemperatureLevel, TemperatureReading

THEMES = {
    "Midnight Violet": {
        "bg": "#0b0b0d",
        "panel": "#151519",
        "border": "#34343b",
        "text": "#f2f2f2",
        "muted": "#a4a4ad",
        "green": "#43d17d",
        "amber": "#efb84d",
        "red": "#ef5b61",
        "accent": "#b68cff",
    },
    "Crimson Cathedral": {
        "bg": "#0d090b",
        "panel": "#1a1115",
        "border": "#4c2934",
        "text": "#f6eef1",
        "muted": "#bea5ad",
        "green": "#4bd47b",
        "amber": "#e5ad55",
        "red": "#f05d73",
        "accent": "#e0526d",
    },
    "Emerald Terminal": {
        "bg": "#070b08",
        "panel": "#101812",
        "border": "#284630",
        "text": "#edf8ef",
        "muted": "#96b29d",
        "green": "#57e389",
        "amber": "#e6bd59",
        "red": "#ee6068",
        "accent": "#57e389",
    },
    "Obsidian Gold": {
        "bg": "#0c0b08",
        "panel": "#191711",
        "border": "#4b4025",
        "text": "#f7f1df",
        "muted": "#b9ae8d",
        "green": "#6bd38a",
        "amber": "#e4b94f",
        "red": "#ec665e",
        "accent": "#dfb850",
    },
}
COLORS = dict(THEMES["Midnight Violet"])


def activate_theme(name: str) -> str:
    selected = name if name in THEMES else "Midnight Violet"
    COLORS.clear()
    COLORS.update(THEMES[selected])
    return selected


def state_color(state: HealthState | str) -> str:
    value = state.value if isinstance(state, HealthState) else state
    if value == HealthState.ONLINE.value:
        return COLORS["green"]
    if value == HealthState.OFFLINE.value:
        return COLORS["red"]
    return COLORS["amber"]


def status_icon(color: str, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 64
    shield = QPainterPath(QPointF(32 * scale, 3 * scale))
    shield.lineTo(56 * scale, 12 * scale)
    shield.lineTo(53 * scale, 34 * scale)
    shield.cubicTo(
        51 * scale,
        47 * scale,
        43 * scale,
        56 * scale,
        32 * scale,
        61 * scale,
    )
    shield.cubicTo(
        21 * scale,
        56 * scale,
        13 * scale,
        47 * scale,
        11 * scale,
        34 * scale,
    )
    shield.lineTo(8 * scale, 12 * scale)
    shield.closeSubpath()
    outline = QPen(QColor(color), max(2.5, 4.0 * scale))
    outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline)
    painter.setBrush(QColor("#111116"))
    painter.drawPath(shield)

    signal_pen = QPen(QColor(color), max(2.0, 3.5 * scale))
    signal_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(signal_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(
        QRectF(16 * scale, 19 * scale, 32 * scale, 25 * scale), 45 * 16, 90 * 16
    )
    painter.drawArc(
        QRectF(23 * scale, 27 * scale, 18 * scale, 14 * scale), 45 * 16, 90 * 16
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QPointF(32 * scale, 42 * scale), 3.5 * scale, 3.5 * scale)
    painter.end()
    return QIcon(pixmap)


def app_style() -> str:
    return f"""
QWidget {{ background: {COLORS["bg"]}; color: {COLORS["text"]}; font-size: 13px; }}
QFrame#card {{ background: {COLORS["panel"]}; border: 1px solid {COLORS["border"]}; border-radius: 9px; }}
QLabel#muted {{ color: {COLORS["muted"]}; }}
QPushButton {{ background: #25252c; border: 1px solid #43434c; border-radius: 6px; padding: 7px 11px; }}
QPushButton:hover {{ border-color: {COLORS["accent"]}; background: #303038; }}
QCheckBox {{ spacing: 8px; }}
QComboBox {{ background: #25252c; border: 1px solid #43434c; border-radius: 6px; padding: 7px 10px; min-width: 105px; }}
QComboBox QAbstractItemView {{ background: {COLORS["panel"]}; color: {COLORS["text"]}; selection-background-color: #34343d; }}
QSpinBox {{ background: #25252c; border: 1px solid #43434c; border-radius: 6px; padding: 7px 10px; min-width: 80px; }}
QScrollArea {{ border: none; }}
QMenuBar {{ background: {COLORS["panel"]}; color: {COLORS["text"]}; border-bottom: 1px solid {COLORS["border"]}; padding: 2px; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: #34343d; border-radius: 4px; }}
QGroupBox {{ border: 1px solid {COLORS["border"]}; border-radius: 7px; margin-top: 10px; padding-top: 12px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {COLORS["accent"]}; }}
QLineEdit {{ background: #111116; border: 1px solid {COLORS["border"]}; border-radius: 5px; padding: 7px; }}
QMenu {{ background: {COLORS["panel"]}; color: {COLORS["text"]}; border: 1px solid {COLORS["border"]}; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 10px; }}
QMenu::item:selected {{ background: #34343d; }}
QProgressBar {{ background: #111116; border: 1px solid {COLORS["border"]}; border-radius: 6px; color: {COLORS["text"]}; min-height: 20px; text-align: center; }}
QProgressBar::chunk {{ background: {COLORS["accent"]}; border-radius: 5px; }}
"""


class AdapterCard(QFrame):
    reconnect_requested = pyqtSignal(str, str)
    prefer_requested = pyqtSignal(str)

    def __init__(
        self, health: AdapterHealth, speed_sample: SpeedSample | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(health.device.name)
        name.setFont(QFont(name.font().family(), 12, QFont.Weight.Bold))
        top.addWidget(name)
        top.addStretch(1)
        layout.addLayout(top)

        connection = health.device.connection or "Not connected"
        connection_label = QLabel(f"Network: {connection}")
        connection_label.setObjectName("muted")
        connection_label.setWordWrap(True)
        connection_label.setToolTip(connection)
        layout.addWidget(connection_label)

        status = health.health.value.upper()
        if health.is_default:
            status += "  •  ACTIVE ROUTE"
        status_label = QLabel(status)
        status_label.setStyleSheet(
            f"color: {state_color(health.health)}; font-weight: 700;"
        )
        layout.addWidget(status_label)

        details: list[str] = []
        if health.latency_ms is not None:
            details.append(f"{health.latency_ms:.0f} ms")
        if health.route_metric is not None:
            details.append(f"route metric {health.route_metric}")
        if health.probe_method != "none":
            details.append(health.probe_method)
        detail_label = QLabel("  •  ".join(details) or health.detail)
        detail_label.setObjectName("muted")
        detail_label.setToolTip(health.detail)
        layout.addWidget(detail_label)

        if speed_sample and speed_sample.success and speed_sample.mbps is not None:
            measured = (
                datetime.fromtimestamp(speed_sample.timestamp, UTC)
                .astimezone()
                .strftime("%I:%M %p")
                .lstrip("0")
            )
            speed_label = QLabel(
                f"Last sample: {speed_sample.mbps:.1f} Mbps down at {measured}"
            )
            speed_label.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 600;")
            layout.addWidget(speed_label)

        buttons = QHBoxLayout()
        reconnect = QPushButton("Reconnect")
        reconnect.setMinimumSize(112, 35)
        reconnect.setEnabled(bool(health.device.connection))
        reconnect.clicked.connect(
            lambda: self.reconnect_requested.emit(
                health.device.name, health.device.connection
            )
        )
        if health.is_default:
            prefer_text = "Already preferred"
            prefer_enabled = False
            prefer_tip = "This adapter already carries the active/default route."
        elif health.health is not HealthState.ONLINE:
            prefer_text = "Unavailable while offline"
            prefer_enabled = False
            prefer_tip = (
                "An adapter must be online before it can become the preferred route."
            )
        else:
            prefer_text = "Make preferred"
            prefer_enabled = True
            prefer_tip = (
                "Updates the saved route metrics for the connected Wi-Fi profiles."
            )
        prefer = QPushButton(prefer_text)
        prefer.setMinimumSize(138, 35)
        prefer.setEnabled(prefer_enabled)
        prefer.setToolTip(prefer_tip)
        prefer.clicked.connect(lambda: self.prefer_requested.emit(health.device.name))
        buttons.addWidget(reconnect)
        buttons.addWidget(prefer)
        buttons.addStretch(1)
        layout.addLayout(buttons)


class SpeedPanel(QFrame):
    run_requested = pyqtSignal()
    interval_changed = pyqtSignal(int)

    def __init__(self, interval_minutes: int) -> None:
        super().__init__()
        self._last_sample: SpeedSample | None = None
        self._latency_ms: float | None = None
        self._running = False
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(7)

        title_row = QHBoxLayout()
        title = QLabel("LIGHTWEIGHT SPEED SAMPLE")
        title.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 700;")
        self.run_button = QPushButton("Run sample now")
        self.run_button.setMinimumSize(138, 35)
        self.run_button.clicked.connect(self.run_requested)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.run_button)
        layout.addLayout(title_row)

        self.value = QLabel("Waiting for the active connection…")
        self.value.setFont(QFont(self.value.font().family(), 16, QFont.Weight.Bold))
        metric_row = QHBoxLayout()
        self.quality = QLabel("QUALITY: MEASURING")
        self.quality.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 700;")
        metric_row.addWidget(self.value)
        metric_row.addStretch(1)
        metric_row.addWidget(self.quality)
        layout.addLayout(metric_row)

        self.detail = QLabel("Download-only, 2 MB maximum per sample.")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

        controls = QHBoxLayout()
        interval_label = QLabel("Automatic sample:")
        interval_label.setObjectName("muted")
        self.interval = QComboBox()
        for label, minutes in (
            ("Off", 0),
            ("Every 5 min", 5),
            ("Every 15 min", 15),
            ("Every 30 min", 30),
            ("Every 60 min", 60),
        ):
            self.interval.addItem(label, minutes)
        selected = self.interval.findData(interval_minutes)
        self.interval.setCurrentIndex(
            selected if selected >= 0 else self.interval.findData(15)
        )
        self.schedule = QLabel("First sample runs after the active route is stable.")
        self.schedule.setObjectName("muted")
        controls.addWidget(interval_label)
        controls.addWidget(self.interval)
        controls.addSpacing(8)
        controls.addWidget(self.schedule, 1)
        layout.addLayout(controls)
        self.interval.currentIndexChanged.connect(
            lambda: self.interval_changed.emit(int(self.interval.currentData()))
        )

    def set_running(self, running: bool, device: str = "") -> None:
        self._running = running
        self.run_button.setEnabled(not running)
        if running:
            self.value.setText(f"Sampling {device}…")
            self.detail.setText(
                "Downloading at most 2 MB without running an upload test."
            )

    def update_sample(self, sample: SpeedSample) -> None:
        self._running = False
        self._last_sample = sample
        self.run_button.setEnabled(True)
        measured = (
            datetime.fromtimestamp(sample.timestamp, UTC)
            .astimezone()
            .strftime("%I:%M:%S %p")
            .lstrip("0")
        )
        if sample.success and sample.mbps is not None:
            self.value.setText(f"{sample.mbps:.1f} Mbps download")
            self.value.setStyleSheet(f"color: {COLORS['green']};")
            self.detail.setText(
                f"{sample.connection} via {sample.device} • {sample.bytes_downloaded / 1_000_000:.1f} MB • {measured}"
            )
        else:
            self.value.setText("Speed sample unavailable")
            self.value.setStyleSheet(f"color: {COLORS['amber']};")
            self.detail.setText(sample.detail)
        self._refresh_quality()

    def set_active_sample(
        self, sample: SpeedSample | None, connection: str = ""
    ) -> None:
        if self._running:
            return
        if sample is not None:
            if self._last_sample != sample:
                self.update_sample(sample)
            return
        self._last_sample = None
        self.value.setText("Waiting for a speed sample…")
        self.value.setStyleSheet("")
        self.detail.setText(
            f"{connection} has not been sampled yet."
            if connection
            else "No active connection is available."
        )
        self._refresh_quality()

    def set_active_latency(self, latency_ms: float | None) -> None:
        self._latency_ms = latency_ms
        self._refresh_quality()

    def _refresh_quality(self) -> None:
        sample = self._last_sample
        if (
            not sample
            or not sample.success
            or sample.mbps is None
            or self._latency_ms is None
        ):
            self.quality.setText("QUALITY: MEASURING")
            self.quality.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 700;")
            return
        if sample.mbps >= 25 and self._latency_ms <= 60:
            label, color = "EXCELLENT", COLORS["green"]
        elif sample.mbps >= 10 and self._latency_ms <= 120:
            label, color = "GOOD", COLORS["green"]
        elif sample.mbps >= 3 and self._latency_ms <= 220:
            label, color = "FAIR", COLORS["amber"]
        else:
            label, color = "POOR", COLORS["red"]
        self.quality.setText(f"QUALITY: {label}")
        self.quality.setStyleSheet(f"color: {color}; font-weight: 700;")

    def set_schedule(self, text: str) -> None:
        self.schedule.setText(text)


class TemperaturePanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("SYSTEM THERMALS")
        title.setFont(QFont(title.font().family(), 11, QFont.Weight.Bold))
        self.state = QLabel("READING SENSOR")
        self.state.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 700;")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.state)
        layout.addLayout(top)

        self.value = QLabel("CPU TEMP: -- °C")
        self.value.setFont(QFont(self.value.font().family(), 17, QFont.Weight.Bold))
        layout.addWidget(self.value)
        self.detail = QLabel("Reading Linux hardware-monitor sensors every five seconds.")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

    def update_reading(
        self, reading: TemperatureReading, level: TemperatureLevel
    ) -> None:
        if reading.celsius is None:
            self.value.setText("CPU TEMP: UNAVAILABLE")
            self.value.setStyleSheet(f"color: {COLORS['muted']};")
            self.state.setText("NO SENSOR")
            self.state.setStyleSheet(
                f"color: {COLORS['muted']}; font-weight: 700;"
            )
            self.detail.setText(reading.detail)
            return
        labels = {
            TemperatureLevel.NORMAL: ("NORMAL", COLORS["green"]),
            TemperatureLevel.HIGH: ("HIGH — COOL ASAP", COLORS["amber"]),
            TemperatureLevel.CRITICAL: ("CRITICAL — COOL NOW", COLORS["red"]),
        }
        label, color = labels.get(level, ("READING", COLORS["muted"]))
        self.value.setText(f"CPU TEMP: {reading.celsius:.1f} °C")
        self.value.setStyleSheet(f"color: {color};")
        self.state.setText(label)
        self.state.setStyleSheet(f"color: {color}; font-weight: 700;")
        source = reading.source or "Linux hardware monitor"
        self.detail.setText(f"Sensor: {source} • {reading.detail}")


class StatusWindow(QMainWindow):
    reconnect_requested = pyqtSignal(str, str)
    prefer_requested = pyqtSignal(str)
    auto_failover_changed = pyqtSignal(bool)
    check_requested = pyqtSignal()
    speed_test_requested = pyqtSignal()
    speed_interval_changed = pyqtSignal(int)
    open_log_requested = pyqtSignal()
    open_diagnostic_log_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    about_requested = pyqtSignal()
    update_check_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    autostart_changed = pyqtSignal(bool)
    auto_update_changed = pyqtSignal(bool)
    temperature_alert_test_requested = pyqtSignal()

    def __init__(
        self,
        automatic_failover: bool,
        speed_interval_minutes: int,
        autostart_enabled: bool,
        auto_update_checks: bool,
    ) -> None:
        super().__init__()
        self.setWindowTitle("DeadSpot Sentinel")
        self.setMinimumSize(550, 570)
        self.resize(640, 760)
        self._adapter_layout: QVBoxLayout | None = None
        self._last_snapshot: NetworkSnapshot | None = None
        self._build_menu(autostart_enabled, auto_update_checks)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        emblem = QLabel()
        emblem.setPixmap(status_icon(COLORS["accent"], 42).pixmap(42, 42))
        title = QLabel("DEADSPOT SENTINEL")
        title.setFont(QFont(title.font().family(), 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']}; letter-spacing: 1px;")
        header.addWidget(emblem)
        header.addSpacing(3)
        header.addWidget(title)
        header.addStretch(1)
        outer.addLayout(header)

        self.summary = QLabel("Starting network monitor…")
        self.summary.setFont(QFont(self.summary.font().family(), 14, QFont.Weight.Bold))
        outer.addWidget(self.summary)

        self.subtitle = QLabel("Reading NetworkManager and testing both Wi-Fi paths.")
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        outer.addWidget(self.subtitle)

        self.temperature_panel = TemperaturePanel()
        outer.addWidget(self.temperature_panel)

        self.speed_panel = SpeedPanel(speed_interval_minutes)
        self.speed_panel.run_requested.connect(self.speed_test_requested)
        self.speed_panel.interval_changed.connect(self.speed_interval_changed)
        outer.addWidget(self.speed_panel)

        adapter_host = QWidget()
        self._adapter_layout = QVBoxLayout(adapter_host)
        self._adapter_layout.setContentsMargins(0, 0, 0, 0)
        self._adapter_layout.setSpacing(9)
        outer.addWidget(adapter_host)

        self.auto_failover = QCheckBox(
            "Automatically promote a working standby adapter"
        )
        self.auto_failover.setChecked(automatic_failover)
        self.auto_failover.setToolTip(
            "Requires two connected Wi-Fi profiles. Promotion changes their saved NetworkManager route metrics."
        )
        self.auto_failover.toggled.connect(self.auto_failover_changed)
        outer.addWidget(self.auto_failover)

        note = QLabel(
            "Automatic failover waits for two complete probe failures and does not automatically fail back, "
            "which helps prevent route flapping."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        outer.addWidget(note)

        controls = QHBoxLayout()
        check = QPushButton("Check now")
        check.clicked.connect(self.check_requested)
        hide = QPushButton("Hide to tray")
        hide.clicked.connect(self.hide)
        controls.addWidget(check)
        controls.addStretch(1)
        controls.addWidget(hide)
        outer.addLayout(controls)

        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        self.setWindowIcon(status_icon(COLORS["accent"]))

    def _build_menu(self, autostart_enabled: bool, auto_update_checks: bool) -> None:
        file_menu = self.menuBar().addMenu("&File")
        refresh = file_menu.addAction("Refresh Status")
        refresh.setShortcut("F5")
        refresh.triggered.connect(lambda: self.check_requested.emit())
        speed = file_menu.addAction("Run Speed Sample")
        speed.triggered.connect(lambda: self.speed_test_requested.emit())
        self.open_log_action = file_menu.addAction("Open Activity Log")
        self.open_log_action.triggered.connect(lambda: self.open_log_requested.emit())
        diagnostic_log = file_menu.addAction("Open Diagnostic Log")
        diagnostic_log.triggered.connect(
            lambda: self.open_diagnostic_log_requested.emit()
        )
        file_menu.addSeparator()
        close_to_tray = file_menu.addAction("Close to Tray")
        close_to_tray.setShortcut("Ctrl+W")
        close_to_tray.triggered.connect(self.hide)
        exit_program = file_menu.addAction("Exit Program")
        exit_program.setShortcut("Ctrl+Q")
        exit_program.triggered.connect(lambda: self.exit_requested.emit())

        settings_menu = self.menuBar().addMenu("&Settings")
        preferences = settings_menu.addAction("Preferences…")
        preferences.triggered.connect(lambda: self.settings_requested.emit())
        test_temperature = settings_menu.addAction("Test Temperature Alert…")
        test_temperature.triggered.connect(
            lambda: self.temperature_alert_test_requested.emit()
        )
        settings_menu.addSeparator()
        self.autostart_action = settings_menu.addAction("Open on Startup")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(autostart_enabled)
        self.autostart_action.toggled.connect(self.autostart_changed)
        self.auto_update_action = settings_menu.addAction(
            "Automatically Install Verified Updates"
        )
        self.auto_update_action.setCheckable(True)
        self.auto_update_action.setChecked(auto_update_checks)
        self.auto_update_action.toggled.connect(self.auto_update_changed)

        about_menu = self.menuBar().addMenu("&About")
        check_updates = about_menu.addAction("Check for Updates…")
        check_updates.triggered.connect(lambda: self.update_check_requested.emit())
        about_menu.addSeparator()
        about = about_menu.addAction("About DeadSpot Sentinel…")
        about.triggered.connect(lambda: self.about_requested.emit())

    def set_autostart_state(self, enabled: bool) -> None:
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(enabled)
        self.autostart_action.blockSignals(False)

    def set_auto_update_state(self, enabled: bool) -> None:
        self.auto_update_action.blockSignals(True)
        self.auto_update_action.setChecked(enabled)
        self.auto_update_action.blockSignals(False)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def update_snapshot(
        self,
        snapshot: NetworkSnapshot,
        speed_samples: dict[str, SpeedSample] | None = None,
    ) -> None:
        self._last_snapshot = snapshot
        active = snapshot.default_adapter
        self.speed_panel.set_active_latency(active.latency_ms if active else None)
        active_sample = None
        if active:
            active_key = f"{active.device.name}\0{active.device.connection}"
            active_sample = (speed_samples or {}).get(active_key)
        self.speed_panel.set_active_sample(
            active_sample, active.device.connection if active else ""
        )
        if snapshot.collection_error:
            self.summary.setText("MONITOR NEEDS ATTENTION")
            self.summary.setStyleSheet(f"color: {COLORS['amber']};")
            self.subtitle.setText(snapshot.collection_error)
        elif snapshot.system_online:
            active = snapshot.default_device or "an available adapter"
            self.summary.setText("YOU ARE ONLINE")
            self.summary.setStyleSheet(f"color: {COLORS['green']};")
            self.subtitle.setText(f"Current default route: {active}")
        elif snapshot.standby_only:
            backup = snapshot.best_online_backup
            self.summary.setText("ACTIVE ROUTE FAILED")
            self.summary.setStyleSheet(f"color: {COLORS['amber']};")
            self.subtitle.setText(
                f"{backup.device.name if backup else 'A standby adapter'} is online and available for failover."
            )
        else:
            self.summary.setText("INTERNET CONNECTION LOST")
            self.summary.setStyleSheet(f"color: {COLORS['red']};")
            self.subtitle.setText(
                "Neither connected Wi-Fi path passed the internet checks."
            )

        assert self._adapter_layout is not None
        while self._adapter_layout.count():
            item = self._adapter_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for health in snapshot.adapters:
            key = f"{health.device.name}\0{health.device.connection}"
            card = AdapterCard(health, (speed_samples or {}).get(key))
            card.reconnect_requested.connect(self.reconnect_requested)
            card.prefer_requested.connect(self.prefer_requested)
            self._adapter_layout.addWidget(card)
        self._adapter_layout.addStretch(1)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        theme: str,
        autostart_enabled: bool,
        notify_when_restored: bool,
        speed_interval_minutes: int,
        temperature_alerts_enabled: bool,
        temperature_warning_c: int,
        temperature_critical_c: int,
        auto_update_checks: bool,
        auto_install_updates: bool,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeadSpot Sentinel Preferences")
        self.setMinimumWidth(540)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        general = QGroupBox("General")
        general_layout = QVBoxLayout(general)
        self.autostart = QCheckBox("Open DeadSpot Sentinel when XFCE starts")
        self.autostart.setChecked(autostart_enabled)
        self.notify_restored = QCheckBox("Show a popup when internet access returns")
        self.notify_restored.setChecked(notify_when_restored)
        general_layout.addWidget(self.autostart)
        general_layout.addWidget(self.notify_restored)
        outer.addWidget(general)

        appearance = QGroupBox("Appearance and Sampling")
        appearance_form = QFormLayout(appearance)
        self.theme = QComboBox()
        self.theme.addItems(THEMES.keys())
        selected_theme = self.theme.findText(theme)
        self.theme.setCurrentIndex(max(selected_theme, 0))
        self.speed_interval = QComboBox()
        for label, minutes in (
            ("Off", 0),
            ("Every 5 minutes", 5),
            ("Every 15 minutes", 15),
            ("Every 30 minutes", 30),
            ("Every 60 minutes", 60),
        ):
            self.speed_interval.addItem(label, minutes)
        selected_interval = self.speed_interval.findData(speed_interval_minutes)
        self.speed_interval.setCurrentIndex(
            selected_interval if selected_interval >= 0 else 2
        )
        appearance_form.addRow("Theme:", self.theme)
        appearance_form.addRow("Speed sample schedule:", self.speed_interval)
        outer.addWidget(appearance)

        thermals = QGroupBox("CPU Temperature")
        thermals_form = QFormLayout(thermals)
        self.temperature_alerts = QCheckBox("Show high-temperature alerts")
        self.temperature_alerts.setChecked(temperature_alerts_enabled)
        self.temperature_warning = QSpinBox()
        self.temperature_warning.setRange(60, 100)
        self.temperature_warning.setSuffix(" °C")
        self.temperature_warning.setValue(temperature_warning_c)
        self.temperature_critical = QSpinBox()
        self.temperature_critical.setRange(65, 110)
        self.temperature_critical.setSuffix(" °C")
        self.temperature_critical.setValue(temperature_critical_c)
        self.temperature_warning.valueChanged.connect(
            lambda value: self.temperature_critical.setMinimum(value + 1)
        )
        self.temperature_critical.setMinimum(self.temperature_warning.value() + 1)
        thermals_form.addRow(self.temperature_alerts)
        thermals_form.addRow("High warning:", self.temperature_warning)
        thermals_form.addRow("Critical warning:", self.temperature_critical)
        thermal_note = QLabel(
            "Sentinel reads Linux hardware sensors locally. Alert recovery uses a 5 °C buffer to prevent repeated popups."
        )
        thermal_note.setObjectName("muted")
        thermal_note.setWordWrap(True)
        thermals_form.addRow(thermal_note)
        outer.addWidget(thermals)

        updates = QGroupBox("Updates")
        updates_layout = QVBoxLayout(updates)
        self.auto_updates = QCheckBox("Automatically check for new releases")
        self.auto_updates.setChecked(auto_update_checks)
        updates_layout.addWidget(self.auto_updates)
        self.auto_install_updates = QCheckBox(
            "Automatically download, verify, install, and restart"
        )
        self.auto_install_updates.setChecked(auto_install_updates)
        self.auto_install_updates.toggled.connect(
            lambda enabled: self.auto_updates.setChecked(
                enabled or self.auto_updates.isChecked()
            )
        )
        updates_layout.addWidget(self.auto_install_updates)
        update_note = QLabel(
            "Updates are locked to the official doctorsus31337/deadspot-sentinel GitHub releases. "
            "Every package must match its published SHA-256 digest and pass archive safety checks before installation."
        )
        update_note.setObjectName("muted")
        update_note.setWordWrap(True)
        updates_layout.addWidget(update_note)
        outer.addWidget(updates)

        restart_note = QLabel(
            "Changing the theme restarts the application automatically after saving."
        )
        restart_note.setObjectName("muted")
        restart_note.setWordWrap(True)
        outer.addWidget(restart_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict[str, object]:
        return {
            "theme": self.theme.currentText(),
            "autostart_enabled": self.autostart.isChecked(),
            "notify_when_restored": self.notify_restored.isChecked(),
            "speed_interval_minutes": int(self.speed_interval.currentData()),
            "temperature_alerts_enabled": self.temperature_alerts.isChecked(),
            "temperature_warning_c": self.temperature_warning.value(),
            "temperature_critical_c": self.temperature_critical.value(),
            "auto_update_checks": self.auto_updates.isChecked(),
            "auto_install_updates": self.auto_install_updates.isChecked(),
        }


def show_about_dialog(parent: QWidget, version: str) -> None:
    QMessageBox.about(
        parent,
        "About DeadSpot Sentinel",
        f"""
        <h2 style='color:{COLORS["accent"]}'>DeadSpot Sentinel</h2>
        <p><b>Version {version}</b></p>
        <p>A dual-adapter network watchdog, connection-quality dashboard, and assisted failover companion.</p>
        <p><b>Created by DoctorSUS &amp; ChatGPT</b></p>
        <p>DoctorSUS brainstormed this application due to his complete lack of patience for living in an
        internet dead spot. He needed a better solution than discovering an outage after everything had
        already crashed—and that is when this wonderfully impatient brainchild was born.</p>
        <p><i>“SHOW ME WHAT YOU GOT.” mode: permanently engaged.</i></p>
        """,
    )


class AlertPopup(QFrame):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("card")
        self.setFixedWidth(370)
        self.setStyleSheet(
            app_style() + f"QFrame#card {{ border: 2px solid {COLORS['red']}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        self.title = QLabel("Internet connection lost")
        self.title.setFont(QFont(self.title.font().family(), 13, QFont.Weight.Bold))
        self.body = QLabel()
        self.body.setObjectName("muted")
        self.body.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Starting…")
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.action = QPushButton()
        self.action.hide()
        self.dismiss = QPushButton("Dismiss")
        self.dismiss.clicked.connect(self.hide)
        buttons.addWidget(self.action)
        buttons.addStretch(1)
        buttons.addWidget(self.dismiss)
        layout.addLayout(buttons)
        self._callback: Callable[[], None] | None = None
        self.action.clicked.connect(self._run_action)

    def _run_action(self) -> None:
        callback = self._callback
        self.hide()
        if callback:
            callback()

    def show_alert(
        self,
        title: str,
        body: str,
        color: str,
        action_label: str = "",
        callback: Callable[[], None] | None = None,
    ) -> None:
        self.progress.hide()
        self.title.setText(title)
        self.body.setText(body)
        self.setStyleSheet(
            app_style() + f"QFrame#card {{ border: 2px solid {color}; }}"
        )
        self._callback = callback
        self.action.setText(action_label)
        self.action.setVisible(bool(action_label and callback))
        self.adjustSize()
        self._move_to_corner()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_progress_alert(self, title: str, body: str, color: str) -> None:
        self.show_alert(title, body, color)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Starting…")
        self.progress.show()
        self.adjustSize()
        self._move_to_corner()

    def update_progress(self, message: str, percent: int) -> None:
        self.body.setText(message)
        if percent < 0:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Downloading…")
        else:
            value = max(0, min(100, percent))
            self.progress.setRange(0, 100)
            self.progress.setValue(value)
            self.progress.setFormat(f"{value}%")
        self.adjustSize()
        self._move_to_corner()

    def _move_to_corner(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(
                area.right() - self.width() - 18, area.bottom() - self.height() - 18
            )


class TrayController:
    def __init__(self, parent: QWidget) -> None:
        self.tray = QSystemTrayIcon(status_icon(COLORS["amber"]), parent)
        self.menu = QMenu(parent)
        self.status_action = QAction("Starting network monitor…", self.menu)
        self.status_action.setEnabled(False)
        self.temperature_action = QAction("CPU temperature: reading…", self.menu)
        self.temperature_action.setEnabled(False)
        self.open_action = QAction("Open status", self.menu)
        self.check_action = QAction("Check now", self.menu)
        self.speed_action = QAction("Run speed sample", self.menu)
        self.adapter_menu = self.menu.addMenu("Wi-Fi adapters")
        self.menu.insertAction(self.adapter_menu.menuAction(), self.status_action)
        self.menu.insertAction(self.adapter_menu.menuAction(), self.temperature_action)
        self.menu.insertSeparator(self.adapter_menu.menuAction())
        self.menu.addAction(self.open_action)
        self.menu.addAction(self.check_action)
        self.menu.addAction(self.speed_action)
        self.menu.addSeparator()
        self.quit_action = QAction("Quit", self.menu)
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("DeadSpot Sentinel is starting")
        self.tray.activated.connect(self._activated)
        self._network_text = "Starting network monitor…"
        self._temperature_text = "CPU temperature: reading…"

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_action.trigger()

    def update_snapshot(
        self,
        snapshot: NetworkSnapshot,
        reconnect: Callable[[str, str], None],
        prefer: Callable[[str], None],
        speed_samples: dict[str, SpeedSample] | None = None,
    ) -> None:
        if snapshot.collection_error:
            color = COLORS["amber"]
            text = "Monitor needs attention"
        elif snapshot.system_online:
            color = COLORS["green"]
            text = f"Online via {snapshot.default_device or 'Wi-Fi'}"
            active = snapshot.default_adapter
            if active:
                key = f"{active.device.name}\0{active.device.connection}"
                sample = (speed_samples or {}).get(key)
                if sample and sample.success and sample.mbps is not None:
                    text += f" • {sample.mbps:.1f} Mbps"
        elif snapshot.standby_only:
            color = COLORS["amber"]
            text = "Active route failed; standby is online"
        else:
            color = COLORS["red"]
            text = "Internet connection lost"
        self.tray.setIcon(status_icon(color))
        self._network_text = text
        self._refresh_tooltip()
        self.status_action.setText(text)
        self.adapter_menu.clear()
        for health in snapshot.adapters:
            marker = "●" if health.health is HealthState.ONLINE else "○"
            active = " — active" if health.is_default else ""
            submenu = self.adapter_menu.addMenu(
                f"{marker} {health.device.name}{active}"
            )
            description = QAction(
                health.device.connection or health.health.value, submenu
            )
            description.setEnabled(False)
            submenu.addAction(description)
            reconnect_action = submenu.addAction("Reconnect")
            reconnect_action.setEnabled(bool(health.device.connection))
            reconnect_action.triggered.connect(
                lambda _checked=False, d=health.device.name, c=health.device.connection: (
                    reconnect(d, c)
                )
            )
            prefer_action = submenu.addAction("Make preferred")
            if health.is_default:
                prefer_action.setText("Already preferred")
                prefer_action.setEnabled(False)
            elif health.health is not HealthState.ONLINE:
                prefer_action.setText("Unavailable while offline")
                prefer_action.setEnabled(False)
            else:
                prefer_action.setEnabled(True)
            prefer_action.triggered.connect(
                lambda _checked=False, d=health.device.name: prefer(d)
            )

    def update_temperature(
        self, reading: TemperatureReading, level: TemperatureLevel
    ) -> None:
        if reading.celsius is None:
            self._temperature_text = "CPU temperature unavailable"
        else:
            suffix = {
                TemperatureLevel.HIGH: " — HIGH",
                TemperatureLevel.CRITICAL: " — CRITICAL",
            }.get(level, "")
            self._temperature_text = f"CPU {reading.celsius:.1f} °C{suffix}"
        self.temperature_action.setText(self._temperature_text)
        self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        self.tray.setToolTip(
            f"DeadSpot Sentinel — {self._network_text} • {self._temperature_text}"
        )
