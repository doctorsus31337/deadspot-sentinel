from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum

CommandRunner = Callable[[Sequence[str], float], "CommandResult"]
SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def run_command(command: Sequence[str], timeout: float = 3.0) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        return CommandResult(127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(124, stdout, stderr or "command timed out")


def split_nmcli_line(line: str) -> list[str]:
    """Split nmcli's terse escaped format without losing spaces in profile names."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line.rstrip("\n"):
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


class HealthState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WifiDevice:
    name: str
    state: str
    connection: str

    @property
    def connected(self) -> bool:
        return self.state.startswith("connected")


@dataclass(frozen=True, slots=True)
class DefaultRoute:
    device: str
    gateway: str
    metric: int


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    device: WifiDevice
    health: HealthState
    latency_ms: float | None
    probe_method: str
    detail: str
    is_default: bool
    route_metric: int | None


@dataclass(frozen=True, slots=True)
class SpeedSample:
    device: str
    connection: str
    success: bool
    mbps: float | None
    bytes_downloaded: int
    duration_seconds: float | None
    timestamp: float
    detail: str


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    timestamp: float
    adapters: tuple[AdapterHealth, ...]
    default_device: str
    collection_error: str = ""

    @property
    def any_online(self) -> bool:
        return any(item.health is HealthState.ONLINE for item in self.adapters)

    @property
    def system_online(self) -> bool:
        """Whether ordinary traffic through the current default route is online."""
        active = self.default_adapter
        return active.health is HealthState.ONLINE if active else self.any_online

    @property
    def standby_only(self) -> bool:
        return self.any_online and not self.system_online

    @property
    def default_adapter(self) -> AdapterHealth | None:
        return next(
            (item for item in self.adapters if item.device.name == self.default_device),
            None,
        )

    @property
    def best_online_backup(self) -> AdapterHealth | None:
        candidates = [
            item
            for item in self.adapters
            if item.health is HealthState.ONLINE
            and item.device.name != self.default_device
        ]
        return min(
            candidates,
            key=lambda item: (
                item.route_metric if item.route_metric is not None else 999999,
                item.latency_ms if item.latency_ms is not None else 999999.0,
            ),
            default=None,
        )


def parse_wifi_devices(output: str) -> list[WifiDevice]:
    devices: list[WifiDevice] = []
    for line in output.splitlines():
        values = split_nmcli_line(line)
        if (
            len(values) >= 4
            and values[1] == "wifi"
            and not values[0].startswith("p2p-")
        ):
            devices.append(WifiDevice(values[0], values[2], values[3]))
    return devices


def parse_default_routes(output: str) -> list[DefaultRoute]:
    try:
        rows = json.loads(output or "[]")
    except json.JSONDecodeError:
        return []
    routes: list[DefaultRoute] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("dev"):
            continue
        try:
            metric = int(row.get("metric", 0))
        except (TypeError, ValueError):
            metric = 0
        routes.append(
            DefaultRoute(str(row["dev"]), str(row.get("gateway", "")), metric)
        )
    return sorted(routes, key=lambda route: route.metric)


class NetworkInspector:
    def __init__(self, runner: CommandRunner = run_command) -> None:
        self.runner = runner

    def devices(self) -> tuple[list[WifiDevice], str]:
        result = self.runner(
            [
                "nmcli",
                "-t",
                "--escape",
                "yes",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
            ],
            2.0,
        )
        if result.returncode != 0:
            return [], result.stderr.strip() or "nmcli could not read device status"
        return parse_wifi_devices(result.stdout), ""

    def routes(self) -> list[DefaultRoute]:
        result = self.runner(["ip", "-j", "-4", "route", "show", "default"], 2.0)
        return parse_default_routes(result.stdout) if result.returncode == 0 else []

    def _ping(self, interface: str) -> tuple[bool, float | None, str]:
        started = time.monotonic()
        result = self.runner(
            ["ping", "-n", "-I", interface, "-c", "1", "-W", "1", "1.1.1.1"], 1.5
        )
        elapsed = (time.monotonic() - started) * 1000
        if result.returncode == 0:
            match = re.search(r"time[=<]([0-9.]+)\s*ms", result.stdout)
            latency = float(match.group(1)) if match else elapsed
            return True, latency, "Cloudflare ping succeeded"
        return False, None, result.stderr.strip() or "ICMP probe failed"

    def _http(self, interface: str) -> tuple[bool, float | None, str]:
        started = time.monotonic()
        result = self.runner(
            [
                "curl",
                "--interface",
                interface,
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                "--connect-timeout",
                "1",
                "--max-time",
                "1.4",
                "http://connectivitycheck.gstatic.com/generate_204",
            ],
            1.8,
        )
        elapsed = (time.monotonic() - started) * 1000
        status = result.stdout.strip()
        if result.returncode == 0 and status == "204":
            return True, elapsed, "HTTP connectivity check returned 204"
        if result.returncode == 0 and status:
            return (
                False,
                None,
                f"Connectivity check returned HTTP {status}; a captive portal may be present",
            )
        return False, None, result.stderr.strip() or "HTTP connectivity check failed"

    def probe(self, device: WifiDevice, route: DefaultRoute | None) -> AdapterHealth:
        if not device.connected:
            return AdapterHealth(
                device,
                HealthState.DISCONNECTED,
                None,
                "none",
                device.state,
                False,
                route.metric if route else None,
            )
        ping_ok, latency, ping_detail = self._ping(device.name)
        if ping_ok:
            return AdapterHealth(
                device,
                HealthState.ONLINE,
                latency,
                "ICMP",
                ping_detail,
                False,
                route.metric if route else None,
            )
        http_ok, latency, http_detail = self._http(device.name)
        return AdapterHealth(
            device,
            HealthState.ONLINE if http_ok else HealthState.OFFLINE,
            latency,
            "HTTP" if http_ok else "ICMP + HTTP",
            http_detail if http_detail else ping_detail,
            False,
            route.metric if route else None,
        )

    def collect(self) -> NetworkSnapshot:
        devices, error = self.devices()
        routes = self.routes()
        route_by_device = {route.device: route for route in routes}
        default_device = routes[0].device if routes else ""
        if not devices:
            return NetworkSnapshot(
                time.time(), (), default_device, error or "No Wi-Fi adapters were found"
            )

        health_by_device: dict[str, AdapterHealth] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(devices))) as executor:
            futures = {
                executor.submit(
                    self.probe, device, route_by_device.get(device.name)
                ): device.name
                for device in devices
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    health_by_device[name] = future.result()
                except (
                    Exception
                ) as exc:  # keep the tray alive if an OS command behaves unexpectedly
                    device = next(item for item in devices if item.name == name)
                    health_by_device[name] = AdapterHealth(
                        device,
                        HealthState.UNKNOWN,
                        None,
                        "error",
                        str(exc),
                        name == default_device,
                        route_by_device.get(name).metric
                        if name in route_by_device
                        else None,
                    )

        adapters: list[AdapterHealth] = []
        for device in devices:
            item = health_by_device[device.name]
            adapters.append(
                AdapterHealth(
                    item.device,
                    item.health,
                    item.latency_ms,
                    item.probe_method,
                    item.detail,
                    device.name == default_device,
                    item.route_metric,
                )
            )
        return NetworkSnapshot(time.time(), tuple(adapters), default_device, error)


class ThroughputSampler:
    """Run a bounded download-only sample against Cloudflare's measurement edge."""

    def __init__(self, runner: CommandRunner = run_command) -> None:
        self.runner = runner

    def measure(
        self, device: str, connection: str, sample_bytes: int = 2_000_000
    ) -> SpeedSample:
        now = time.time()
        if not SAFE_INTERFACE.fullmatch(device):
            return SpeedSample(
                device,
                connection,
                False,
                None,
                0,
                None,
                now,
                "The adapter name is not valid for an interface-bound speed sample.",
            )
        bounded_bytes = min(max(int(sample_bytes), 250_000), 10_000_000)
        endpoint = (
            "https://speed.cloudflare.com/__down"
            f"?bytes={bounded_bytes}&cachebust={int(now * 1000)}"
        )
        result = self.runner(
            [
                "curl",
                "--interface",
                device,
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}|%{size_download}|%{speed_download}|%{time_total}",
                "--header",
                "Cache-Control: no-cache",
                "--connect-timeout",
                "2",
                "--max-time",
                "12",
                endpoint,
            ],
            13.0,
        )
        if result.returncode != 0:
            return SpeedSample(
                device,
                connection,
                False,
                None,
                0,
                None,
                now,
                result.stderr.strip() or "The lightweight speed sample failed.",
            )
        try:
            status, downloaded_text, speed_text, duration_text = (
                result.stdout.strip().split("|")
            )
            downloaded = int(float(downloaded_text))
            bytes_per_second = float(speed_text)
            duration = float(duration_text)
        except (TypeError, ValueError):
            return SpeedSample(
                device,
                connection,
                False,
                None,
                0,
                None,
                now,
                "curl returned an unreadable speed measurement.",
            )
        if status != "200" or downloaded < bounded_bytes * 0.9 or bytes_per_second <= 0:
            return SpeedSample(
                device,
                connection,
                False,
                None,
                downloaded,
                duration,
                now,
                f"The measurement endpoint returned HTTP {status} with {downloaded} bytes.",
            )
        mbps = bytes_per_second * 8 / 1_000_000
        return SpeedSample(
            device,
            connection,
            True,
            mbps,
            downloaded,
            duration,
            now,
            f"Bounded {downloaded / 1_000_000:.1f} MB download sample via {device}.",
        )


class RecoveryManager:
    PRIMARY_METRIC = 50
    STANDBY_METRIC = 600

    def __init__(self, runner: CommandRunner = run_command) -> None:
        self.runner = runner

    @staticmethod
    def _valid_device(device: str) -> bool:
        return bool(SAFE_INTERFACE.fullmatch(device))

    def reconnect(self, device: str, connection: str) -> tuple[bool, str]:
        if not self._valid_device(device) or not connection:
            return False, "A valid adapter and saved connection are required."
        result = self.runner(
            ["nmcli", "connection", "up", "id", connection, "ifname", device], 20.0
        )
        if result.returncode == 0:
            return True, f"Reconnected {device} to {connection}."
        return (
            False,
            result.stderr.strip()
            or result.stdout.strip()
            or "NetworkManager could not reconnect the adapter.",
        )

    def prefer(
        self, target: AdapterHealth, adapters: Sequence[AdapterHealth]
    ) -> tuple[bool, str]:
        if not self._valid_device(target.device.name) or not target.device.connection:
            return (
                False,
                "The selected adapter does not have a usable saved connection.",
            )
        changed: list[tuple[str, str]] = []
        for item in adapters:
            if (
                not item.device.connected
                or not item.device.connection
                or not self._valid_device(item.device.name)
            ):
                continue
            metric = (
                self.PRIMARY_METRIC
                if item.device.name == target.device.name
                else self.STANDBY_METRIC
            )
            result = self.runner(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    item.device.connection,
                    "ipv4.route-metric",
                    str(metric),
                    "ipv6.route-metric",
                    str(metric),
                ],
                5.0,
            )
            if result.returncode != 0:
                return (
                    False,
                    result.stderr.strip()
                    or f"Could not update {item.device.connection}.",
                )
            changed.append((item.device.name, item.device.connection))

        for device, _connection in changed:
            self.runner(["nmcli", "device", "reapply", device], 8.0)

        result = self.runner(
            [
                "nmcli",
                "connection",
                "up",
                "id",
                target.device.connection,
                "ifname",
                target.device.name,
            ],
            20.0,
        )
        if result.returncode != 0:
            return (
                False,
                result.stderr.strip() or "The preferred route could not be activated.",
            )
        return (
            True,
            f"{target.device.name} is now preferred. Saved NetworkManager route metrics were updated.",
        )
