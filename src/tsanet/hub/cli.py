"""``tsanet-hub`` entry point.

Parses config and CLI flags, then starts the hub server.  The hub owns USB
serial connections to tinySA devices and exposes them over the network.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import Annotated, Optional

try:
    import typer
except ImportError:
    sys.exit(
        "typer is not installed.\n"
        "Install it with:  pip install typer\n"
        "or reinstall:      pip install --force-reinstall tsanet"
    )

from tsanet.common.config import NetworkConfig
from tsanet.common.errors import SecurityNotImplementedError
from tsanet.common.logging import configure as configure_logging
from tsanet.hub.config import DEFAULT_CONFIG_PATH, HubConfig
from tsanet.hub.server import HubServer

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger("tsanet.hub")


def main() -> None:
    """Run the tsanet hub (Typer entry point for the console script)."""
    app()


def _resolve_log_level(
    verbose: bool,
    debug: bool,
    log_level: str,
) -> int:
    """Resolve effective log level from flags.
    Priority: --debug > --verbose > --log-level > default (WARNING).
    """
    if debug:
        return logging.DEBUG
    if verbose:
        return logging.INFO
    try:
        return getattr(logging, log_level.upper())
    except AttributeError:
        return logging.WARNING


@app.command()
def run(
    config_path: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to hub config YAML"),
    ] = None,
    mode: Annotated[
        Optional[str],
        typer.Option("--mode", help="Network mode: listen or dial"),
    ] = None,
    transport: Annotated[
        Optional[str],
        typer.Option("--transport", help="Network transport: tcp or unix"),
    ] = None,
    address: Annotated[
        Optional[str],
        typer.Option("--address", help="Bind or connect address"),
    ] = None,
    port: Annotated[
        Optional[int],
        typer.Option("--port", help="TCP port"),
    ] = None,
    poll_interval: Annotated[
        Optional[float],
        typer.Option("--poll-interval", help="Device hotplug scan interval (seconds)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show informational messages"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show detailed debug output (implies --verbose)"),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Log level: debug, info, warning, error (overridden by --verbose/--debug)",
        ),
    ] = "warning",
) -> None:
    level = _resolve_log_level(verbose, debug, log_level)
    configure_logging(level)

    config = HubConfig.load(config_path or DEFAULT_CONFIG_PATH)

    if config_path is None and not DEFAULT_CONFIG_PATH.exists():
        logger.info("no config file found at %s, using defaults", DEFAULT_CONFIG_PATH)

    if mode is not None:
        config.network.mode = mode  # type: ignore[assignment]
    if transport is not None:
        config.network.transport = transport  # type: ignore[assignment]
    if address is not None:
        config.network.address = address
    if port is not None:
        config.network.port = port
    if poll_interval is not None:
        config.poll_interval = poll_interval

    NetworkConfig.model_validate(config.network.__dict__)

    server = HubServer(config)

    def _handle_signal(signum: int, frame: object) -> None:
        logger.info("received signal %s", signal.Signals(signum).name)
        server.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        server.start()
    except SecurityNotImplementedError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
