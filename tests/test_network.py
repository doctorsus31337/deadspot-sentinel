import json
import time
import unittest

from deadspot_sentinel.network import (
    AdapterHealth,
    CommandResult,
    HealthState,
    NetworkSnapshot,
    RecoveryManager,
    ThroughputSampler,
    WifiDevice,
    parse_default_routes,
    parse_wifi_devices,
    split_nmcli_line,
)


class NmcliParsingTests(unittest.TestCase):
    def test_split_preserves_spaces_and_unescapes_colons(self):
        self.assertEqual(
            split_nmcli_line(r"wlan0:wifi:connected:Motel\: Guest WiFi"),
            ["wlan0", "wifi", "connected", "Motel: Guest WiFi"],
        )

    def test_only_real_wifi_devices_are_returned(self):
        output = "\n".join(
            [
                "wlan0:wifi:connected:Primary Lab WiFi ",
                "wlan1:wifi:connected:Backup Hotspot",
                "p2p-dev-wlan1:wifi-p2p:disconnected:",
                "tailscale0:tun:connected (externally):tailscale0",
            ]
        )
        devices = parse_wifi_devices(output)
        self.assertEqual([item.name for item in devices], ["wlan0", "wlan1"])
        self.assertEqual(devices[0].connection, "Primary Lab WiFi ")


class RouteParsingTests(unittest.TestCase):
    def test_routes_are_sorted_by_metric(self):
        output = json.dumps(
            [
                {
                    "dst": "default",
                    "gateway": "192.168.2.1",
                    "dev": "wlan1",
                    "metric": 600,
                },
                {
                    "dst": "default",
                    "gateway": "10.0.0.1",
                    "dev": "wlan0",
                    "metric": 100,
                },
            ]
        )
        routes = parse_default_routes(output)
        self.assertEqual(routes[0].device, "wlan0")
        self.assertEqual(routes[1].metric, 600)


class SnapshotStateTests(unittest.TestCase):
    def test_online_standby_does_not_hide_failed_default_route(self):
        snapshot = NetworkSnapshot(
            time.time(),
            (
                AdapterHealth(
                    WifiDevice("wlan0", "connected", "Primary"),
                    HealthState.OFFLINE,
                    None,
                    "ICMP + HTTP",
                    "failed",
                    True,
                    50,
                ),
                AdapterHealth(
                    WifiDevice("wlan1", "connected", "Standby"),
                    HealthState.ONLINE,
                    20.0,
                    "ICMP",
                    "ok",
                    False,
                    600,
                ),
            ),
            "wlan0",
        )
        self.assertTrue(snapshot.any_online)
        self.assertFalse(snapshot.system_online)
        self.assertTrue(snapshot.standby_only)
        self.assertEqual(snapshot.best_online_backup.device.name, "wlan1")


class RecoveryTests(unittest.TestCase):
    def test_prefer_uses_argument_lists_and_assigns_expected_metrics(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "ok", "")

        primary = AdapterHealth(
            WifiDevice("wlan0", "connected", "Primary Lab WiFi "),
            HealthState.ONLINE,
            25.0,
            "ICMP",
            "ok",
            True,
            100,
        )
        standby = AdapterHealth(
            WifiDevice("wlan1", "connected", "Backup Hotspot"),
            HealthState.ONLINE,
            18.0,
            "ICMP",
            "ok",
            False,
            600,
        )
        ok, _message = RecoveryManager(fake_runner).prefer(standby, (primary, standby))
        self.assertTrue(ok)
        modify_calls = [
            command
            for command, _timeout in calls
            if command[1:3] == ["connection", "modify"]
        ]
        self.assertIn("Primary Lab WiFi ", modify_calls[0])
        self.assertIn("600", modify_calls[0])
        self.assertIn("Backup Hotspot", modify_calls[1])
        self.assertIn("50", modify_calls[1])
        self.assertTrue(all(isinstance(command, list) for command, _timeout in calls))


class ThroughputSamplerTests(unittest.TestCase):
    def test_successful_sample_converts_bytes_per_second_to_mbps(self):
        calls = []

        def fake_runner(command, timeout):
            calls.append((list(command), timeout))
            return CommandResult(0, "200|2000000|1250000|1.6", "")

        sample = ThroughputSampler(fake_runner).measure(
            "wlan1", "Backup Hotspot", 2_000_000
        )
        self.assertTrue(sample.success)
        self.assertAlmostEqual(sample.mbps, 10.0)
        self.assertIn("--interface", calls[0][0])
        self.assertIn("wlan1", calls[0][0])
        self.assertIn("bytes=2000000", calls[0][0][-1])

    def test_partial_download_is_not_reported_as_a_valid_speed(self):
        def fake_runner(_command, _timeout):
            return CommandResult(0, "200|500000|1000000|0.5", "")

        sample = ThroughputSampler(fake_runner).measure("wlan0", "Primary", 2_000_000)
        self.assertFalse(sample.success)
        self.assertIsNone(sample.mbps)


if __name__ == "__main__":
    unittest.main()
