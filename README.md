# DeadSpot Sentinel

DeadSpot Sentinel is a compact PyQt6 tray utility for NetworkManager Linux
desktops. It watches each Wi-Fi adapter independently, warns immediately when an
internet path dies, assists with dual-adapter failover, and samples connection
quality without running a heavyweight speed test.

Created by **DoctorSUS & ChatGPT**.

DoctorSUS brainstormed this application due to his lack of patience for living
in an internet dead spot. He needed a better solution than discovering an outage
after everything had already crashed—and that is when this brainchild was born.

## Highlights in v0.4.2

- Roughly one-second connectivity checks with interface-bound ICMP and HTTP probes.
- Distinct green, amber, and red sentinel-shield tray states.
- Persistent desktop popups for connection loss and restoration.
- Dual-Wi-Fi status, reconnect controls, route preference, and opt-in failover.
- Lightweight 2 MB download-only throughput samples on the active route.
- Four themes, XFCE autostart, activity logs, and a terminal-free launcher.
- A five-second CPU-temperature monitor using Linux hardware sensors, with
  configurable high and critical thresholds, hysteresis, tray status, and
  persistent **HIGH TEMP — COOL ASAP** alerts.
- A 15-second cold-login tray grace period that eliminates false “no system tray”
  warnings while XFCE is still starting.
- Background release polling every six hours when update checks are enabled, so
  post-v0.4.1 updates can install without restarting or manually checking.
- Live download, checksum, archive-safety, and extraction progress in the update
  popup, including an indeterminate fallback when a server omits file size.
- A repository-locked updater that verifies SHA-256 and rejects unsafe ZIP paths,
  symlinks, oversized archives, and incomplete packages before installation.
- GitHub Actions CI plus automatic versioned release and update-manifest creation.

## Install on Kali or Debian-family Linux

Install the operating-system prerequisites:

```bash
sudo apt update
sudo apt install python3-venv network-manager curl iputils-ping libegl1 libxcb-cursor0
```

Download and extract a release, then run:

```bash
chmod +x install.sh
./install.sh
```

To install and open it automatically at XFCE login:

```bash
./install.sh --autostart
```

Launch it from the XFCE Applications menu or run:

```bash
~/.local/bin/deadspot-sentinel
```

That command detaches immediately; no terminal window stays open. Troubleshooting
options are available when needed:

```bash
~/.local/bin/deadspot-sentinel --foreground
~/.local/bin/deadspot-sentinel --diagnostic-log
```

## Updates

The one-time upgrade from v0.3.1 to v0.4.0 must be installed manually because
v0.3.1 contains only a manifest checker. Starting with v0.4.0, enable
**Settings → Automatically Install Verified Updates** to let future releases
download, verify, install, and restart without a terminal.

Because the already-published v0.4.0 checks at startup but does not poll again
while continuously running, the v0.4.0 → v0.4.1 live test requires one manual
**About → Check for Updates** after v0.4.1 is published. Version 0.4.1 adds a
six-hour background poll, so subsequent releases are fully hands-off while the
automatic-update checkbox remains enabled.

The updater accepts only the release manifest and versioned ZIP assets published
by `doctorsus31337/deadspot-sentinel`. It checks the package against the manifest's
SHA-256 digest and validates its contents before launching the external installer.
This protects against accidental corruption and feed redirection; as with any
GitHub-delivered updater, repository-account and GitHub security remain part of
the trust boundary.

Merging a new version into `main` runs the release workflow. The workflow validates
the source, builds `deadspot-sentinel-vVERSION.zip`, generates `update.json`, tags
the commit, and publishes both assets in a GitHub Release. If that version already
exists, the workflow exits without overwriting it.

## Speed samples

Automatic samples are download-only and capped at 2 MB. They run against the
active/default Wi-Fi adapter using Cloudflare's measurement endpoint. The default
schedule is every 15 minutes, with Off, 5, 30, and 60-minute choices. This is a
bounded connection-quality estimate, not a saturation benchmark.

## Failover behavior

**Make preferred** changes saved NetworkManager IPv4 and IPv6 route metrics: the
selected connected profile receives metric `50`, and other connected Wi-Fi
profiles receive `600`. A success or failure popup reports the result. Local
policy may deny this operation; if so, the diagnostic log records the application
output and the GUI reports the failed action.

Automatic failover is opt-in. It waits for two complete probe failures, uses a
cooldown, and does not automatically fail back, which reduces route flapping.
Switching public IP addresses cannot guarantee that arbitrary TCP downloads
survive; clients with retry and resume support have the best chance of continuing.

## Development

Run the network and updater tests without an active network connection:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_release.py --output-dir dist
```

The application itself requires Python 3.11 or later and PyQt6 6.7 or later.

## CPU temperature monitoring

Sentinel reads CPU-focused sensors exposed through Linux `hwmon`, with a thermal
zone fallback. It does not install a daemon or run a recurring shell command.
The hottest recognized CPU sensor is shown in the main dashboard and tray menu.

Defaults are **85 °C** for high and **95 °C** for critical. Both values and the
alert toggle are available under **Settings → Preferences**. After an alert,
the temperature must fall at least 5 °C below the warning boundary before the
state returns to normal; this prevents popup spam while a reading hovers near a
threshold. Missing or unsupported sensors are reported as unavailable and never
produce a heat warning.

Use **Settings → Test Temperature Alert…** to verify the popup safely without
heating the CPU or writing a simulated incident to the activity log.

## License

[MIT](LICENSE)
