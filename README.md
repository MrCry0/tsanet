# tsanet

Network control suite for tinySA spectrum analyzers.

`tsanet` lets one or more tinySA units, physically attached via USB to one
machine, be discovered, indexed, and remotely controlled from another machine
(or the same machine) over a network.

## Components

The suite is one Python package (`tsanet`) exposing three console scripts:

- `tsanet-hub` - runs on the machine with tinySA units plugged in. Owns the
  USB serial connections, discovers and indexes connected devices, and
  executes commands received over the network.
- `tsanet-ctl` - command-line controller that issues commands to a hub.
- `tsanet-gui` - graphical controller with the same command set, plus a live
  spectrum graph and trace statistics.

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

Phases 1–7 are implemented and tested:

- Device serial protocol: command framing, echo and prompt handling, retries,
  text and binary responses. Full verified tinySA wire command vocabulary.
- Version probing, model identification, RGB565 framebuffer decoding, and a
  stdlib-only PNG encoder for screenshots.
- Device discovery and hub-side registry with hotplug polling.
- MessagePack-framed network transport over TCP and Unix sockets, with
  listen/dial symmetry so the hub can operate behind NAT.
- Hub server with single-session management, force-takeover, auto-device
  selection, and automatic LNA enable for sweep frequencies above 800 MHz.
- RPC dispatcher routing all domain operations (device, sweep, marker, trace,
  signal, menu, preset, capture, raw, devices, session).
- Live-graph subscription push loop with frequency caching and interval pacing.
- Controller CLI (`tsanet-ctl`) with 50+ commands across all RPC domains,
  frequency parsing (1.5ghz, 250k, 433.92mhz), and unit-aware trace stats.
- Controller GUI (`tsanet-gui`) with connection dialog, device panel, sweep
  controls, screenshot capture, live spectrum graph, and trace statistics.

Remaining: security hardening (token/TLS), packaging (PyInstaller), reconnect
and idle-timeout logic, and integration tests against real hardware.

## Installation

tsanet is not yet published to a package index, so install it from the Git
repository. Installing the suite as a tool provides the three console scripts
on your PATH. Choose extras to match the role of the machine:

- `hub` - serial support (`pyserial`), for a machine with tinySA units.
- `gui` - the graphical controller (`PySide6`, `pyqtgraph`).
- `cli` - the command-line controller (`typer`).
- `all` - all of the above.

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
controller can start issuing commands immediately.

### Controller CLI

Connect to a hub and control the device:

```sh
# List devices and check session
tsanet-ctl --address 127.0.0.1 --port 7777 devices list
tsanet-ctl --address 127.0.0.1 --port 7777 session status

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

Opens a tabbed window with device listing, sweep controls, trace settings,
screenshot capture, live spectrum graph (3 configurable lines, max-speed or
fixed-interval updates), and trace statistics.

## Configuration

Settings come from a YAML file, overridable by command-line flags:

- Hub: `~/.config/tsanet/hub.yaml`
- Controller: `~/.config/tsanet/controller.yaml`

```yaml
network:
  mode: listen        # listen | dial
  transport: tcp       # tcp | unix
  address: 0.0.0.0
  port: 7777
security:
  mode: none           # none | token | tls-token
  token: null
```

## Development

This project uses [uv](https://docs.astral.sh/uv/):

```sh
uv sync --all-extras     # create .venv with all extras + dev tools
uv run ruff check .       # lint
uv run ruff format .      # format
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
