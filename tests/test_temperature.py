import tempfile
import unittest
from pathlib import Path

from deadspot_sentinel.temperature import (
    TemperatureLevel,
    TemperatureReader,
    next_temperature_level,
    normalize_temperature,
)


class TemperatureValueTests(unittest.TestCase):
    def test_normalize_accepts_linux_millidegrees(self):
        self.assertEqual(normalize_temperature("72500\n"), 72.5)

    def test_normalize_rejects_impossible_values(self):
        self.assertIsNone(normalize_temperature("999999999"))
        self.assertIsNone(normalize_temperature("not-a-number"))

    def test_alert_levels_use_hysteresis(self):
        self.assertIs(
            next_temperature_level(86, TemperatureLevel.NORMAL, 85, 95),
            TemperatureLevel.HIGH,
        )
        self.assertIs(
            next_temperature_level(82, TemperatureLevel.HIGH, 85, 95),
            TemperatureLevel.HIGH,
        )
        self.assertIs(
            next_temperature_level(79, TemperatureLevel.HIGH, 85, 95),
            TemperatureLevel.NORMAL,
        )
        self.assertIs(
            next_temperature_level(97, TemperatureLevel.NORMAL, 85, 95),
            TemperatureLevel.CRITICAL,
        )


class TemperatureReaderTests(unittest.TestCase):
    def test_reader_chooses_hottest_cpu_hwmon_sensor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hwmon = root / "hwmon" / "hwmon0"
            hwmon.mkdir(parents=True)
            (hwmon / "name").write_text("coretemp\n", encoding="utf-8")
            (hwmon / "temp1_label").write_text("Package id 0\n", encoding="utf-8")
            (hwmon / "temp1_input").write_text("68000\n", encoding="utf-8")
            (hwmon / "temp2_label").write_text("Core 0\n", encoding="utf-8")
            (hwmon / "temp2_input").write_text("73500\n", encoding="utf-8")
            reading = TemperatureReader(
                root / "hwmon", root / "thermal"
            ).read()
            self.assertEqual(reading.celsius, 73.5)
            self.assertIn("Core 0", reading.source)

    def test_reader_falls_back_to_a_cpu_thermal_zone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zone = root / "thermal" / "thermal_zone0"
            zone.mkdir(parents=True)
            (zone / "type").write_text("x86_pkg_temp\n", encoding="utf-8")
            (zone / "temp").write_text("61\n", encoding="utf-8")
            reading = TemperatureReader(root / "hwmon", root / "thermal").read()
            self.assertEqual(reading.celsius, 61.0)
            self.assertEqual(reading.source, "x86_pkg_temp")

    def test_reader_reports_unavailable_without_a_supported_sensor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reading = TemperatureReader(root / "hwmon", root / "thermal").read()
            self.assertFalse(reading.available)


if __name__ == "__main__":
    unittest.main()
