from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar


class TemperatureLevel(Enum):
    UNAVAILABLE = "unavailable"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    celsius: float | None
    source: str = ""
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.celsius is not None


def normalize_temperature(raw: str) -> float | None:
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    while abs(value) > 1_000:
        value /= 1_000
    if -20 <= value <= 150:
        return round(value, 1)
    return None


def next_temperature_level(
    celsius: float | None,
    previous: TemperatureLevel,
    warning_c: int,
    critical_c: int,
    hysteresis_c: int = 5,
) -> TemperatureLevel:
    if celsius is None:
        return TemperatureLevel.UNAVAILABLE
    if celsius >= critical_c:
        return TemperatureLevel.CRITICAL
    if previous is TemperatureLevel.CRITICAL and celsius >= critical_c - hysteresis_c:
        return TemperatureLevel.CRITICAL
    if celsius >= warning_c:
        return TemperatureLevel.HIGH
    if previous in {TemperatureLevel.HIGH, TemperatureLevel.CRITICAL} and celsius >= (
        warning_c - hysteresis_c
    ):
        return TemperatureLevel.HIGH
    return TemperatureLevel.NORMAL


class TemperatureReader:
    CPU_SENSOR_NAMES: ClassVar[set[str]] = {
        "coretemp",
        "k10temp",
        "zenpower",
        "cpu_thermal",
        "x86_pkg_temp",
    }
    CPU_LABEL_MARKERS: ClassVar[tuple[str, ...]] = (
        "package",
        "tctl",
        "tdie",
        "cpu",
        "core",
    )

    def __init__(
        self,
        hwmon_root: Path = Path("/sys/class/hwmon"),
        thermal_root: Path = Path("/sys/class/thermal"),
    ) -> None:
        self.hwmon_root = hwmon_root
        self.thermal_root = thermal_root

    @staticmethod
    def _text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _hwmon_readings(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for directory in sorted(self.hwmon_root.glob("hwmon*")):
            sensor_name = self._text(directory / "name").lower()
            for input_path in sorted(directory.glob("temp*_input")):
                stem = input_path.stem.removesuffix("_input")
                label = self._text(directory / f"{stem}_label")
                recognized = sensor_name in self.CPU_SENSOR_NAMES or any(
                    marker in label.lower() for marker in self.CPU_LABEL_MARKERS
                )
                if not recognized:
                    continue
                value = normalize_temperature(self._text(input_path))
                if value is not None:
                    source = " ".join(part for part in (sensor_name, label) if part)
                    readings.append(TemperatureReading(value, source or stem))
        return readings

    def _thermal_readings(self) -> list[TemperatureReading]:
        readings: list[TemperatureReading] = []
        for directory in sorted(self.thermal_root.glob("thermal_zone*")):
            sensor_type = self._text(directory / "type").lower()
            if sensor_type not in self.CPU_SENSOR_NAMES and not any(
                marker in sensor_type for marker in self.CPU_LABEL_MARKERS
            ):
                continue
            value = normalize_temperature(self._text(directory / "temp"))
            if value is not None:
                readings.append(TemperatureReading(value, sensor_type))
        return readings

    def read(self) -> TemperatureReading:
        readings = self._hwmon_readings() or self._thermal_readings()
        if not readings:
            return TemperatureReading(
                None,
                detail="No supported CPU temperature sensor was exposed by Linux.",
            )
        hottest = max(readings, key=lambda item: item.celsius or -273)
        return TemperatureReading(
            hottest.celsius,
            hottest.source,
            f"Hottest CPU sensor of {len(readings)} available reading(s).",
        )
