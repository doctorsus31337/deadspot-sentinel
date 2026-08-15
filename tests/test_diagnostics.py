import unittest

from deadspot_sentinel.network import CommandResult, DiagnosticManager


class DiagnosticManagerTests(unittest.TestCase):
    def test_adapter_inventory_combines_networkmanager_kernel_and_wifi_views(self):
        calls = []
        outputs = {
            "nmcli": "wlan0  wifi  connected  Motel WiFi\neth0  ethernet  unavailable  --\n",
            "ip": "wlan0 UP 192.0.2.10/24\neth0 DOWN\n",
            "iw": "Interface wlan0\n\ttype managed\n",
        }

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, outputs[command[0]], "")

        ok, report = DiagnosticManager(fake_runner).adapter_inventory()

        self.assertTrue(ok)
        self.assertIn("NetworkManager devices", report)
        self.assertIn("Kernel interfaces", report)
        self.assertIn("Wi-Fi modes", report)
        self.assertEqual([call[0][0] for call in calls], ["nmcli", "ip", "iw"])

    def test_reset_all_network_adapters_cycles_networkmanager(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).reset_all_adapters()

        self.assertTrue(ok)
        self.assertIn("reset", message.lower())
        self.assertEqual(
            [command for command, _timeout in calls],
            [
                ["nmcli", "networking", "off"],
                ["nmcli", "networking", "on"],
            ],
        )

    def test_reset_all_networking_uses_service_restart_as_recovery(self):
        calls = []
        enable_attempts = 0

        def fake_runner(command, _timeout):
            nonlocal enable_attempts
            calls.append(list(command))
            if list(command) == ["nmcli", "networking", "on"]:
                enable_attempts += 1
                if enable_attempts < 3:
                    return CommandResult(1, "", "could not enable networking")
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).reset_all_adapters()

        self.assertTrue(ok)
        self.assertEqual(calls.count(["nmcli", "networking", "on"]), 3)
        self.assertIn(
            ["pkexec", "systemctl", "restart", "NetworkManager.service"],
            calls,
        )
        self.assertIn("recovered", message.lower())

    def test_reset_all_networking_fails_if_post_restart_enable_fails(self):
        calls = []

        def fake_runner(command, _timeout):
            calls.append(list(command))
            if list(command) == ["nmcli", "networking", "on"]:
                return CommandResult(1, "", "still disabled")
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).reset_all_adapters()

        self.assertFalse(ok)
        self.assertEqual(calls.count(["nmcli", "networking", "on"]), 3)
        self.assertIn("still disabled", message)

    def test_restore_managed_mode_uses_safe_argument_lists(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restore_managed_mode(["wlan1"])

        self.assertTrue(ok)
        self.assertIn("wlan1", message)
        commands = [command for command, _timeout in calls]
        self.assertEqual(
            commands,
            [
                ["pkexec", "ip", "link", "set", "dev", "wlan1", "down"],
                ["pkexec", "iw", "dev", "wlan1", "set", "type", "managed"],
                ["pkexec", "ip", "link", "set", "dev", "wlan1", "up"],
                ["nmcli", "device", "set", "wlan1", "managed", "yes"],
                ["nmcli", "device", "connect", "wlan1"],
            ],
        )
        self.assertTrue(all(isinstance(command, list) for command in commands))

    def test_restore_managed_mode_rejects_unsafe_interface_name(self):
        for invalid in ("wlan0; shutdown", "--help", "-f", "a" * 16):
            with self.subTest(invalid=invalid):
                called = False

                def fake_runner(_command, _timeout):
                    nonlocal called
                    called = True
                    return CommandResult(0, "", "")

                ok, message = DiagnosticManager(fake_runner).restore_managed_mode(
                    [invalid]
                )

                self.assertFalse(ok)
                self.assertIn("invalid", message.lower())
                self.assertFalse(called)

    def test_reconnect_adapter_cycles_selected_device(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).reconnect_adapter("wlan0")

        self.assertTrue(ok)
        self.assertIn("wlan0", message)
        self.assertEqual(
            [command for command, _timeout in calls],
            [
                ["nmcli", "device", "disconnect", "wlan0"],
                ["nmcli", "device", "connect", "wlan0"],
            ],
        )

    def test_restore_all_managed_mode_discovers_monitor_interfaces_with_iw(self):
        calls = []

        def fake_runner(command, _timeout):
            calls.append(list(command))
            if list(command) == ["iw", "dev"]:
                return CommandResult(
                    0,
                    "phy#0\n\tInterface wlan0mon\nphy#1\n\tInterface wlan1\n",
                    "",
                )
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restore_all_managed_mode()

        self.assertTrue(ok)
        self.assertIn("wlan0mon, wlan1", message)
        self.assertIn(
            ["pkexec", "iw", "dev", "wlan0mon", "set", "type", "managed"],
            calls,
        )
        self.assertIn(
            ["pkexec", "iw", "dev", "wlan1", "set", "type", "managed"],
            calls,
        )

    def test_restore_all_rejects_invalid_discovery_before_any_repair(self):
        calls = []

        def fake_runner(command, _timeout):
            calls.append(list(command))
            if list(command) == ["iw", "dev"]:
                return CommandResult(
                    0,
                    "phy#0\n\tInterface wlan0\nphy#1\n\tInterface --help\n",
                    "",
                )
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restore_all_managed_mode()

        self.assertFalse(ok)
        self.assertIn("invalid", message.lower())
        self.assertEqual(calls, [["iw", "dev"]])

    def test_restore_managed_mode_brings_interface_back_up_when_iw_fails(self):
        calls = []

        def fake_runner(command, _timeout):
            calls.append(list(command))
            if list(command)[1:3] == ["iw", "dev"]:
                return CommandResult(1, "", "mode change failed")
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restore_managed_mode(["wlan0"])

        self.assertFalse(ok)
        self.assertIn("mode change failed", message)
        self.assertIn(
            ["pkexec", "ip", "link", "set", "dev", "wlan0", "up"],
            calls,
        )

    def test_restore_managed_mode_retries_up_and_returns_control_to_nm(self):
        calls = []
        up_attempts = 0

        def fake_runner(command, _timeout):
            nonlocal up_attempts
            calls.append(list(command))
            if list(command)[-1] == "up":
                up_attempts += 1
                if up_attempts == 1:
                    return CommandResult(1, "", "temporary up failure")
            return CommandResult(0, "", "")

        ok, _message = DiagnosticManager(fake_runner).restore_managed_mode(["wlan0"])

        self.assertTrue(ok)
        self.assertEqual(up_attempts, 2)
        self.assertIn(["nmcli", "device", "set", "wlan0", "managed", "yes"], calls)
        self.assertIn(["nmcli", "device", "connect", "wlan0"], calls)

    def test_restore_all_attempts_later_interfaces_after_failure(self):
        calls = []

        def fake_runner(command, _timeout):
            calls.append(list(command))
            if list(command) == ["iw", "dev"]:
                return CommandResult(
                    0,
                    "phy#0\n\tInterface wlan0\nphy#1\n\tInterface wlan1\n",
                    "",
                )
            if list(command)[1:4] == ["iw", "dev", "wlan0"]:
                return CommandResult(1, "", "wlan0 mode failure")
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restore_all_managed_mode()

        self.assertFalse(ok)
        self.assertIn("wlan0 mode failure", message)
        self.assertIn(
            ["pkexec", "iw", "dev", "wlan1", "set", "type", "managed"],
            calls,
        )

    def test_restart_networkmanager_requests_polkit_privilege(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "", "")

        ok, message = DiagnosticManager(fake_runner).restart_network_manager()

        self.assertTrue(ok)
        self.assertIn("restarted", message.lower())
        self.assertEqual(
            calls[0][0],
            ["pkexec", "systemctl", "restart", "NetworkManager.service"],
        )

    def test_route_and_dns_report_collects_both_views(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "diagnostic output", "")

        ok, report = DiagnosticManager(fake_runner).route_and_dns_report()

        self.assertTrue(ok)
        self.assertIn("Routes", report)
        self.assertIn("Addressing and DNS", report)
        self.assertEqual([command[0] for command, _timeout in calls], ["ip", "nmcli"])

    def test_partial_report_is_not_reported_as_successful(self):
        def fake_runner(command, _timeout):
            if command[0] == "ip":
                return CommandResult(0, "default via 192.0.2.1", "")
            return CommandResult(1, "", "NetworkManager unavailable")

        ok, report = DiagnosticManager(fake_runner).route_and_dns_report()

        self.assertFalse(ok)
        self.assertIn("default via 192.0.2.1", report)
        self.assertIn("ERROR: NetworkManager unavailable", report)


if __name__ == "__main__":
    unittest.main()
