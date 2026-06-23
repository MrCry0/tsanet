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

Early development, built in phases. Implemented and tested so far:

- Device serial protocol: command framing, echo and prompt handling, retries,
  text and binary responses.
- Command vocabulary: the full verified tinySA wire command set.
- Version probing, model identification, and RGB565 framebuffer decoding.
- Device discovery and a hub-side registry with hotplug polling.
- Packaging and CI.

Not yet built: the network transport, the hub runtime, and the controller CLI
and GUI. The `tsanet-hub`, `tsanet-ctl`, and `tsanet-gui` scripts are installed
but currently report that they are not yet implemented.

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

The hub and controller runtime are still under construction; the sections
below describe the intended workflow.

The hub runs on the machine with tinySA units attached and, by default,
listens for a controller:

```sh
tsanet-hub --mode listen --transport tcp --address 0.0.0.0 --port 7777
```

A controller dials in, lists the indexed devices, selects one, and drives it:

```sh
tsanet-ctl --address hub.example --port 7777 devices list
tsanet-ctl --address hub.example --port 7777 devices select <id>
tsanet-ctl --address hub.example --port 7777 capture save --output screen.png
```

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
uv run pytest             # tests
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
