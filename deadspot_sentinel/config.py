from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "deadspot-sentinel"


def config_dir() -> Path:
    return Path.home() / ".config" / APP_NAME


def state_dir() -> Path:
    return Path.home() / ".local" / "state" / APP_NAME


@dataclass(slots=True)
class AppConfig:
    check_interval_ms: int = 1100
    automatic_failover: bool = False
    preferred_device: str = ""
    failover_failure_threshold: int = 2
    failover_cooldown_seconds: int = 20
    popup_on_primary_failure: bool = True
    speed_sample_interval_minutes: int = 15
    speed_sample_bytes: int = 2_000_000
    temperature_poll_seconds: int = 5
    temperature_alerts_enabled: bool = True
    temperature_warning_c: int = 85
    temperature_critical_c: int = 95
    theme: str = "Midnight Violet"
    notify_when_restored: bool = True
    auto_update_checks: bool = False
    auto_install_updates: bool = False
    last_update_check_timestamp: float = 0.0

    @classmethod
    def load(cls) -> AppConfig:
        path = config_dir() / "config.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = {field.name for field in fields(cls)}
            return cls(**{key: value for key, value in raw.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "config.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(destination)


class OutageLog:
    def __init__(self) -> None:
        self.path = state_dir() / "outages.jsonl"

    def append(self, event: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
