import os
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QTabWidget

from deadspot_sentinel.app import SentinelApp
from deadspot_sentinel.ui import AlertPopup, StatusWindow


class TrayAndAlertBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_window_is_a_tool_window_so_it_never_gets_a_taskbar_entry(self):
        window = StatusWindow(False, 15, False, False)
        self.addCleanup(window.close)

        self.assertEqual(window.windowType(), Qt.WindowType.Tool)

    def test_alert_popup_cannot_take_keyboard_focus(self):
        popup = AlertPopup()
        self.addCleanup(popup.close)

        self.assertTrue(
            bool(popup.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        )
        self.assertTrue(
            popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        )

    def test_dashboard_has_a_real_diagnostics_tab_with_repair_controls(self):
        window = StatusWindow(False, 15, False, False)
        self.addCleanup(window.close)

        tabs = window.findChild(QTabWidget, "main_tabs")
        self.assertIsNotNone(tabs)
        assert tabs is not None
        self.assertEqual(
            [tabs.tabText(i) for i in range(tabs.count())],
            ["Status", "Diagnostics"],
        )

        expected_buttons = {
            "diagnostic_inventory",
            "diagnostic_routes_dns",
            "diagnostic_reconnect",
            "diagnostic_restore_selected",
            "diagnostic_restore_all",
            "diagnostic_reset_all",
            "diagnostic_restart_nm",
        }
        actual_buttons = {
            button.objectName()
            for button in window.findChildren(QPushButton)
            if button.objectName().startswith("diagnostic_")
        }
        self.assertEqual(actual_buttons, expected_buttons)

    def test_reconnect_requires_confirmation_before_running(self):
        run_diagnostic = Mock()
        controller = cast(
            SentinelApp,
            SimpleNamespace(
                window=object(),
                diagnostics=SimpleNamespace(reconnect_adapter=Mock()),
                _run_diagnostic=run_diagnostic,
            ),
        )
        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.No,
        ):
            SentinelApp.diagnostic_reconnect(controller, "wlan0")

        run_diagnostic.assert_not_called()

    def test_reconnect_confirmation_runs_only_selected_adapter(self):
        reconnect = Mock(return_value=(True, "ok"))
        run_diagnostic = Mock()
        controller = cast(
            SentinelApp,
            SimpleNamespace(
                window=object(),
                diagnostics=SimpleNamespace(reconnect_adapter=reconnect),
                _run_diagnostic=run_diagnostic,
            ),
        )
        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            SentinelApp.diagnostic_reconnect(controller, "wlan0")

        run_diagnostic.assert_called_once()
        action = run_diagnostic.call_args.args[0]
        self.assertEqual(action(), (True, "ok"))
        reconnect.assert_called_once_with("wlan0")


if __name__ == "__main__":
    unittest.main()
