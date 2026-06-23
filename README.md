# tsanet

Network control suite for tinySA spectrum analyzers.

`tsanet` lets one or more tinySA units, physically attached via USB to
one machine, be discovered, indexed, and remotely controlled from another
machine (or the same machine) over a network.

## Components

The suite is one Python package (`tsanet`) exposing three console scripts:

- `tsanet-hub` - runs on the machine with tinySA units plugged in. Owns
  the USB serial connections, discovers and indexes connected devices, and
  executes commands received over the network.
- `tsanet-ctl` - command-line controller that issues commands to a hub.
- `tsanet-gui` - graphical controller with the same command set, plus a live
  spectrum graph and trace statistics.

Hub and controller communicate over TCP or a Unix domain socket; either side
can listen or dial out, so the hub can sit behind NAT and connect outward to a
listening controller.

## Status

Early development. The package skeleton, packaging, and CI are in place; the
device, transport, and application layers are being built out in phases.

## Development

This project uses [uv](https://docs.astral.sh/uv/):

```sh
uv sync --all-extras    # create .venv with all extras + dev tools
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pytest            # tests
```

The `all` extra pulls in the hub (`pyserial`), CLI (`typer`), and GUI
(`PySide6`, `pyqtgraph`) dependencies. A headless hub box can sync just the
hub extra: `uv sync --extra hub`.

## License

GPL-2.0-only. See [LICENSE](LICENSE).
