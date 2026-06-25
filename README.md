# tsanet

Network control suite for **tinySA / tinySA Ultra** spectrum analyzers.

`tsanet` lets one or more tinySA units, physically attached via USB to one
machine, be discovered, indexed, and remotely controlled from another machine
(or the same machine) over a network.

## Quick start

Start the hub on the machine with tinySA units attached:
```sh
tsanet-hub --port 7777
```

From any controller machine, open the GUI:
```sh
tsanet-gui
```
And connect to the hub's IP and port in the connection dialog.

Or use the command-line controller for scripting and automation:
```sh
tsanet-ctl --address 127.0.0.1 --port 7777 devices list
tsanet-ctl --address 127.0.0.1 --port 7777 sweep center 433.92mhz
tsanet-ctl --address 127.0.0.1 --port 7777 trace save --trace 1,2 -o sweep.csv
```

[Example configuration files](examples/) are provided for both hub and
controller setups, including token authentication.

## Components

The suite is one Python package (`tsanet`) exposing three console scripts:

- **`tsanet-hub`** — Runs on the machine with tinySA units plugged in. Owns
  the USB serial connections, discovers and indexes connected devices, and
  executes commands received over the network.
- **`tsanet-ctl`** — Command-line controller with 50+ commands across all RPC
  domains, frequency parsing, and unit-aware trace statistics.
- **`tsanet-gui`** — Graphical controller with device listing, sweep controls,
  trace management, screenshot capture, live spectrum graph (up to 3
  configurable trace lines), and trace statistics.

## Architecture

The hub and controller share a transport abstraction. Either side can listen
(act as the network server) or dial out (act as the client), over TCP or a
Unix domain socket. This supports the reverse-connect case where the hub sits
behind NAT and dials out to a listening controller, as well as the usual case
of a controller dialing in to a hub.

Once a connection is open, both sides speak a symmetric request/response/event
protocol regardless of who initiated it: a 4-byte length prefix followed by a
MessagePack payload. MessagePack is used so binary payloads (screenshots, raw
scan dumps) ride natively as bytes. A hub serves a single controller session
at a time.

The device layer is a faithful port of the tinySA USB serial protocol: it
replicates the device's command echo, `ch> ` prompt framing, and post-boot
retry behaviour, and exposes the real wire command vocabulary.

## Status

Phases 1-7 are implemented and tested:

- Device serial protocol: command framing, echo and prompt handling, retries,
  text and binary responses. Full verified tinySA wire command vocabulary.
- Version probing, model identification, RGB565 framebuffer decoding, and a
  stdlib-only PNG encoder for screenshots.
- Device discovery and hub-side registry with hotplug polling.
- MessagePack-framed network transport over TCP and Unix sockets, with
  listen/dial symmetry so the hub can operate behind NAT.
- Hub server with single-session management, force-takeover, auto-device
  selection, and automatic LNA enable for sweep frequencies above 800 MHz.
  Shared-secret token authentication, checked immediately after connection
  establishment.
- RPC dispatcher routing all domain operations (device, sweep, marker, trace,
  signal, menu, preset, capture, raw, devices, session).
- Live-graph subscription push loop with frequency caching and interval pacing.
- Controller CLI (`tsanet-ctl`) with 50+ commands, `--device` selection option,
  frequency parsing (1.5ghz, 250k, 433.92mhz), and unit-aware trace stats.
- Controller GUI (`tsanet-gui`) with connection dialog (including token auth),
  device panel, sweep controls with mismatch warnings, screenshot capture
  (fetch/save/copy), live spectrum graph (3 lines, max-speed or fixed-interval),
  and comprehensive trace statistics dialog.
- Robust error handling: connection failures, invalid frequency arguments,
  firmware rejection of unknown commands, trace parsing errors, and sweep
  value clamping are caught and reported cleanly rather than crashing.

Remaining: TLS (`tls-token` mode is accepted by config validation but the
hub and controller refuse to start with a clear error until it is built),
packaging (PyInstaller), reconnect and idle-timeout logic, and integration
tests against real hardware.

## Security

Three security modes are supported:

| Mode | Auth | Encryption | Use case |
|---|---|---|---|
| `none` | — | — | Trusted loopback or Unix socket |
| `token` | Shared secret | — | Trusted network + peer verification |
| `tls-token` | Shared secret | TLS | Untrusted network (not yet implemented) |

The hub logs a warning if `none` is used over non-loopback TCP.

**Token authentication** is configured by setting the same `token` value in
both `hub.yaml` and `controller.yaml`:
```yaml
security:
  mode: token
  token: a-long-random-shared-secret
```
The check happens immediately after the connection is established. A mismatched
token is rejected on both ends without taking down the hub.

## Installation

tsanet is not yet published to a package index, so install it from the Git
repository. Installing the suite as a tool provides the three console scripts
on your PATH. Choose extras to match the role of the machine:

- `hub` — serial support (`pyserial`), for a machine with tinySA units.
- `cli` — the command-line controller (`typer`).
- `gui` — the graphical controller (`PySide6`, `pyqtgraph`).
- `all` — all of the above.

### uv (recommended)

```sh
# Hub machine (headless): just the serial extra
uv tool install "tsanet[hub] @ git+https://github.com/MrCry0/tsanet"

# Controller workstation: the GUI
uv tool install "tsanet[gui] @ git+https://github.com/MrCry0/tsanet"
```

### pipx

```sh
pipx install "tsanet[all] @ git+https://github.com/MrCry0/tsanet"
```

### pip

```sh
pip install "tsanet[all] @ git+https://github.com/MrCry0/tsanet"
```

## Usage

### Hub

Start the hub on the machine with tinySA units attached. It discovers
connected devices and listens for a controller:

```sh
tsanet-hub --mode listen --transport tcp --address 0.0.0.0 --port 7777
```

The hub auto-selects the only device when exactly one is present, so the
controller can start issuing commands immediately. With more than one
device attached, pass `--device <device_id>` on the controller (see
below) to pick which one a given invocation targets.

### Controller CLI

Connect to a hub and control the device:

```sh
# List devices and check session
tsanet-ctl --address 127.0.0.1 --port 7777 devices list
tsanet-ctl --address 127.0.0.1 --port 7777 session status

# On a hub with more than one device attached, target a specific one
tsanet-ctl --address 127.0.0.1 --port 7777 --device /dev/ttyACM1 sweep get

# Sweep control
tsanet-ctl --address 127.0.0.1 --port 7777 sweep range 100mhz 500mhz --points 450
tsanet-ctl --address 127.0.0.1 --port 7777 sweep center 433.92mhz
tsanet-ctl --address 127.0.0.1 --port 7777 sweep get
# Start:      100.00 MHz
# End:        500.00 MHz
# Center:     300.00 MHz
# Points:     450

# Markers
tsanet-ctl --address 127.0.0.1 --port 7777 marker on 1
tsanet-ctl --address 127.0.0.1 --port 7777 marker peak 1

# Trace data and statistics
tsanet-ctl --address 127.0.0.1 --port 7777 trace calc 1 maxh
tsanet-ctl --address 127.0.0.1 --port 7777 trace save --trace 1,2 -o sweep.csv
tsanet-ctl --address 127.0.0.1 --port 7777 trace stats --trace 2 --start 410.5mhz --stop 600mhz

# Screenshot
tsanet-ctl --address 127.0.0.1 --port 7777 capture save -o screen.png

# High-frequency sweeps (auto-enables LNA above 800 MHz)
tsanet-ctl --address 127.0.0.1 --port 7777 sweep center 1.785ghz
```

### Controller GUI

```sh
tsanet-gui
```

The GUI opens a connection dialog first. After connecting, a tabbed window
provides:

| Tab | Function |
|---|---|
| **Devices** | List attached units with [free]/[BUSY] status; click to select |
| **Sweep** | Set start/stop/points, center, span, or CW frequency. Fields auto-refresh on tab activation and can be manually refreshed. A warning dialog appears if the device silently clamps a requested value. |
| **Trace** | Enable/disable traces (1-4), set calculation modes (minh, maxh, aver4, etc.). Open the **Trace Stats** dialog for detailed analysis. |
| **Capture** | Fetch the device screen (PNG), save to file, or copy to clipboard. |
| **Live Graph** | Real-time spectrum with up to 3 configurable trace lines, max-speed or fixed-interval updates. |

#### Trace statistics

Available from the Trace tab via the "Trace Stats..." button, the statistics
dialog computes (over a selectable frequency sub-range and display unit):

- **Average power** — unit-aware linear averaging (power dB, voltage dB, or linear)
- **Median** — midpoint of the sorted values
- **Min / Max** — with their frequencies
- **Channel power** — total integrated power across the band
- **Occupied bandwidth (99% OBW)** — ITU-R/FCC convention
- **PAPR** — peak-to-average power ratio (crest factor), in dB
- **Flatness** — peak-to-trough variation across the range, in dB
- **Field strength** — dBuV/m, when an antenna factor (dB/m) is provided

See the [CLI trace stats documentation](examples/README.md) for the equivalent
command-line interface and [example scripts](examples/).

## Configuration

Settings come from a YAML file, overridable by command-line flags:

- Hub: `~/.config/tsanet/hub.yaml`
- Controller: `~/.config/tsanet/controller.yaml`

```yaml
network:
  mode: listen        # listen | dial
  transport: tcp      # tcp | unix
  address: 0.0.0.0
  port: 7777
security:
  mode: none          # none | token | tls-token
  token: null
```

[Example configuration files](examples/) with token authentication are
included in the repository.

## Development

This project uses [uv](https://docs.astral.sh/uv/):

```sh
uv sync --all-extras     # create .venv with all extras + dev tools
uv run ruff check .      # lint
uv run ruff format .     # format
uv run --extra cli --extra hub --extra gui pytest  # tests (including GUI imports)
uv run --extra cli --extra hub pytest --ignore=tests/test_hardware.py  # skip PySide6
```

### Running from source

The repo includes executable wrapper scripts at the root that run the three
programs directly without installing the package:

```sh
python tsanet-hub.py --port 7777
python tsanet-ctl.py --address 127.0.0.1 --port 7777 devices list
python tsanet-gui.py
```

These auto-detect the project's `.venv` and re-exec under it, so they work
without activating the virtualenv.

### Hardware tests

```sh
uv run --extra cli --extra hub pytest tests/test_hardware.py --run-hardware
```

`uv sync` installs the `dev` dependency group automatically. The `all` extra
pulls in the hub (`pyserial`), CLI (`typer`), and GUI (`PySide6`, `pyqtgraph`)
dependencies; a headless hub box can sync just the hub extra with
`uv sync --extra hub`.

Prefer pip? The same workflow is available with pip 25.1 or newer:

```sh
pip install -e ".[all]" --group dev
```

## License

GPL-2.0-only. See [LICENSE](LICENSE).
