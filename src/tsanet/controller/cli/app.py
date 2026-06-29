"""``tsanet-ctl`` entry point.

Typer-based CLI with command groups matching the RPC domains.
"""

from __future__ import annotations

import csv
import datetime
import enum
import io
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

try:
    import typer
except ImportError:
    sys.exit(
        "typer is not installed.\n"
        "Install it with:  pip install typer\n"
        "or reinstall:      pip install --force-reinstall tsanet"
    )

from typer._click.globals import get_current_context

from tsanet.common.config import NetworkConfig
from tsanet.common.errors import AuthenticationError, ConnectionClosed, SecurityNotImplementedError
from tsanet.common.logging import configure as configure_logging
from tsanet.controller.config import DEFAULT_CONFIG_PATH, ControllerConfig
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient, RpcError
from tsanet.controller.stats import compute_stats
from tsanet.device.model import VALID_CALC, VALID_UNITS


# -- help formatting -------------------------------------------------------


def _get_help(ctx) -> str:
    """Return the full help text for the current command.

    Builds the help string from the command's parameter metadata so the
    caller can display it without relying on Click's internal formatting.
    """
    cmd = ctx.command
    path = ctx.command_path if hasattr(ctx, "command_path") else cmd.name

    lines = [f"Usage: {path}"]
    for p in cmd.get_params(ctx):
        if getattr(p, "hidden", False):
            continue
        if p.name == "help":
            continue
        flags = ", ".join(p.opts)
        lines.append(f"  {flags:<24s} {p.help or ''}{' [required]' if p.required else ''}")

    desc = (cmd.help or "").strip()
    if desc:
        lines.append("")
        lines.append(f"  {desc}")

    return "\n".join(lines)


# -- enum types for Typer validation --------------------------------------


class NetworkMode(str, enum.Enum):
    listen = "listen"
    dial = "dial"


class TransportKind(str, enum.Enum):
    tcp = "tcp"
    unix = "unix"


class SpurMode(str, enum.Enum):
    on = "on"
    off = "off"
    auto = "auto"


class LnaMode(str, enum.Enum):
    on = "on"
    off = "off"


# Dynamically create Enum types from the device model constants so they
# stay in sync and Typer can validate against them.
_CalcType = enum.Enum("_CalcType", {v: v for v in sorted(VALID_CALC)}, type=str)  # type: ignore[call-overload]
_UnitType = enum.Enum("_UnitType", {v: v for v in sorted(VALID_UNITS)}, type=str)  # type: ignore[call-overload]

app = typer.Typer(no_args_is_help=True)
_client: RpcClient | None = None
_config_path: str | None = None
_network_overrides: dict[str, object] = {}
_selected_device: str | None = None
_log = logging.getLogger("tsanet.ctl")


def _load_config() -> ControllerConfig:
    config = ControllerConfig.load(_config_path or DEFAULT_CONFIG_PATH)
    for key, value in _network_overrides.items():
        setattr(config.network, key, value)
    NetworkConfig.model_validate(config.network.__dict__)
    return config


def _rpc() -> RpcClient:
    global _client
    if _client is not None:
        return _client

    config = _load_config()
    _log.info(
        "connecting to hub: mode=%s transport=%s address=%s",
        config.network.mode,
        config.network.transport,
        config.network.address,
    )

    client = RpcClient(config)
    try:
        client.connect()
        _log.info("connected to hub")
        if _selected_device is not None:
            _log.info("selecting device: %s", _selected_device)
            client.call("devices", "select", device_id=_selected_device)
    except (SecurityNotImplementedError, AuthenticationError, ConnectionClosed, RpcError) as exc:
        _log.error("connection failed: %s", exc)
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        where = (
            f"{config.network.address}:{config.network.port}"
            if config.network.transport == "tcp"
            else config.network.address
        )
        _log.error("could not reach %s: %s", where, exc)
        typer.echo(f"error: could not reach {where}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _client = client
    return _client


def _call(domain: str, op: str, **args: object) -> object:
    _log.info("RPC %s.%s args=%s", domain, op, args)
    _log.debug("sending RPC %s.%s", domain, op)
    try:
        result = _rpc().call(domain, op, **args)
        _log.debug("RPC %s.%s -> %r", domain, op, result)
        return result
    except RpcError as exc:
        _log.error("RPC error %s.%s: %s", domain, op, exc)
        raise typer.Exit(str(exc)) from exc


def _die(msg: str) -> typer.Exit:
    try:
        ctx = get_current_context()
        typer.echo(_get_help(ctx), err=True)
    except RuntimeError:
        pass
    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code=1)


def _freq(raw: str) -> int:
    try:
        return parse_frequency(raw)
    except ValueError as exc:
        _die(str(exc))


# -- callback --------------------------------------------------------------


def _resolve_log_level(verbose: bool, debug: bool) -> int:
    if debug:
        return logging.DEBUG
    if verbose:
        return logging.INFO
    return logging.WARNING


@app.callback(invoke_without_command=True)
def _setup(
    ctx: typer.Context,
    config_path: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to controller config YAML"),
    ] = None,
    mode: Annotated[
        Optional[NetworkMode],
        typer.Option("--mode", help="Network mode: listen or dial"),
    ] = None,
    transport: Annotated[
        Optional[TransportKind],
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
    device: Annotated[
        Optional[str],
        typer.Option(
            "--device",
            "-d",
            help="Device ID to select on a hub with more than one device attached",
        ),
    ] = None,
    list_devices_alias: Annotated[
        bool,
        typer.Option("--devices-list", "-L", help="Alias for the devices-list command"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show informational messages"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show detailed debug output (implies --verbose)"),
    ] = False,
) -> None:
    global _config_path, _network_overrides, _selected_device
    configure_logging(_resolve_log_level(verbose, debug))

    _config_path = config_path
    _network_overrides = {}
    if mode is not None:
        _network_overrides["mode"] = mode
    if transport is not None:
        _network_overrides["transport"] = transport
    if address is not None:
        _network_overrides["address"] = address
    if port is not None:
        _network_overrides["port"] = port
    _selected_device = device

    if list_devices_alias and ctx.invoked_subcommand is None:
        devices_list()
        raise typer.Exit()


# -- device discovery -------------------------------------------------------


@app.command(name="devices-list")
def devices_list() -> None:
    """List indexed tinySA devices on the hub."""
    devices = _call("devices", "list")
    if not devices:
        typer.echo("no devices found")
        return
    for d in devices:
        typer.echo(
            f"{d['device_id']:<20s} {d['model']:<10s} fw={d['firmware'] or '?'}"
            f"  hw={d['hardware']}  {'[BUSY]' if d['busy'] else '[free]'}"
        )


# -- device ----------------------------------------------------------------


device_app = typer.Typer(no_args_is_help=True)
app.add_typer(device_app, name="device", help="Device identification and control")


@device_app.command(name="version")
def device_version() -> None:
    """Print device firmware and hardware version."""
    typer.echo(_call("device", "get_version"))


@device_app.command(name="id")
def device_id(
    new_id: Annotated[
        Optional[int],
        typer.Argument(help="New persistent device ID (omitting it prints the current ID)"),
    ] = None,
) -> None:
    """Get or set the persistent device ID.

    The ID is stored on the tinySA hardware itself, so it remains stable
    across reboots and USB port changes. Use it to target a specific
    device on a multi-device hub regardless of its /dev/ttyACM* path.
    """
    if new_id is not None:
        _call("device", "set_id", id=new_id)
        typer.echo(f"device ID set to {new_id}")
    else:
        typer.echo(_call("device", "get_id"))


@device_app.command(name="battery")
def device_battery() -> None:
    """Print battery voltage and offset."""
    typer.echo(f"voltage: {_call('device', 'get_battery')}")
    typer.echo(f"offset:  {_call('device', 'get_battery_offset')}")


@device_app.command(name="reset")
def device_reset(
    dfu: Annotated[bool, typer.Option("--dfu", help="Reset to DFU bootloader mode")] = False,
) -> None:
    """Reset the device."""
    _call("device", "reset", dfu=dfu)
    typer.echo("reset sent")


# -- sweep -----------------------------------------------------------------


sweep_app = typer.Typer(no_args_is_help=True)
app.add_typer(sweep_app, name="sweep", help="Sweep control")


def _sweep_state() -> tuple[int, int, Optional[int]]:
    """Query the device's actual current sweep start/stop/points.

    Setters report this afterward rather than echoing the requested value,
    since the device can silently clamp it (e.g. a 900-point request is
    capped to its 450-point maximum) without returning an error.
    """
    raw = str(_call("sweep", "get"))
    parts = raw.split()
    try:
        if len(parts) < 2:
            raise ValueError("too few fields")
        start = int(parts[0])
        stop = int(parts[1])
        points = int(parts[2]) if len(parts) > 2 else None
    except ValueError as exc:
        raise typer.Exit(f"unexpected sweep response: {raw!r}") from exc
    return start, stop, points


def _warn_if_mismatch(label: str, requested, actual, fmt=str) -> None:
    """Warn when the device applied something other than what was requested."""
    if requested is not None and actual is not None and requested != actual:
        typer.echo(
            f"warning: requested {label} {fmt(requested)} but device applied {fmt(actual)}",
            err=True,
        )


@sweep_app.command(name="get")
def sweep_get() -> None:
    """Print current sweep settings."""
    start, stop, points = _sweep_state()
    center = (start + stop) // 2
    typer.echo(f"Start:      {_fmt_hz(start)}")
    typer.echo(f"End:        {_fmt_hz(stop)}")
    typer.echo(f"Center:     {_fmt_hz(center)}")
    if points is not None:
        typer.echo(f"Points:     {points}")


@sweep_app.command(name="status")
def sweep_status() -> None:
    """Print sweep status."""
    typer.echo(_call("sweep", "get_status"))


@sweep_app.command(name="start")
def sweep_start(hz: Annotated[str, typer.Argument(help="Start frequency (e.g. 100mhz)")]) -> None:
    """Set sweep start frequency."""
    freq = _freq(hz)
    _call("sweep", "set_start", hz=freq)
    start, _stop, _points = _sweep_state()
    _warn_if_mismatch("start", freq, start, _fmt_hz)
    typer.echo(f"start = {_fmt_hz(start)}")


@sweep_app.command(name="stop")
def sweep_stop(
    hz: Annotated[str, typer.Argument(help="Stop frequency (e.g. 500mhz)")],
) -> None:
    """Set sweep stop frequency."""
    freq = _freq(hz)
    _call("sweep", "set_stop", hz=freq)
    _start, stop, _points = _sweep_state()
    _warn_if_mismatch("stop", freq, stop, _fmt_hz)
    typer.echo(f"stop = {_fmt_hz(stop)}")


@sweep_app.command(name="center")
def sweep_center(
    hz: Annotated[str, typer.Argument(help="Center frequency (e.g. 433.92mhz)")],
) -> None:
    """Set sweep center frequency."""
    freq = _freq(hz)
    _call("sweep", "set_center", hz=freq)
    start, stop, _points = _sweep_state()
    actual_center = (start + stop) // 2
    _warn_if_mismatch("center", freq, actual_center, _fmt_hz)
    typer.echo(f"center = {_fmt_hz(actual_center)}")


@sweep_app.command(name="span")
def sweep_span(hz: Annotated[str, typer.Argument(help="Span (e.g. 100mhz)")]) -> None:
    """Set sweep span."""
    freq = _freq(hz)
    _call("sweep", "set_span", hz=freq)
    start, stop, _points = _sweep_state()
    actual_span = stop - start
    _warn_if_mismatch("span", freq, actual_span, _fmt_hz)
    typer.echo(f"span = {_fmt_hz(actual_span)}")


@sweep_app.command(name="cw")
def sweep_cw(hz: Annotated[str, typer.Argument(help="CW frequency (e.g. 433.92mhz)")]) -> None:
    """Set sweep to continuous-wave mode at a frequency."""
    freq = _freq(hz)
    _call("sweep", "set_cw", hz=freq)
    start, _stop, _points = _sweep_state()
    _warn_if_mismatch("cw frequency", freq, start, _fmt_hz)
    typer.echo(f"cw = {_fmt_hz(start)}")


@sweep_app.command(name="range")
def sweep_range(
    start: Annotated[str, typer.Argument(help="Start frequency (e.g. 100mhz)")],
    stop: Annotated[str, typer.Argument(help="Stop frequency (e.g. 500mhz)")],
    points: Annotated[
        Optional[int],
        typer.Argument(help="Number of points (e.g. 450, default: device maximum)"),
    ] = None,
) -> None:
    """Set sweep start, stop, and optionally point count.

    Example: tsanet-ctl sweep range 100mhz 500mhz 450
    """
    s = _freq(start)
    t = _freq(stop)
    _call("sweep", "set_start_stop", start=s, stop=t, points=points)
    actual_start, actual_stop, actual_points = _sweep_state()
    _warn_if_mismatch("start", s, actual_start, _fmt_hz)
    _warn_if_mismatch("stop", t, actual_stop, _fmt_hz)
    _warn_if_mismatch("points", points, actual_points)
    extra = f" ({actual_points} pts)" if actual_points is not None else ""
    typer.echo(f"range = {_fmt_hz(actual_start)} - {_fmt_hz(actual_stop)}{extra}")


@sweep_app.command(name="time")
def sweep_time(us: Annotated[int, typer.Argument(help="Sweep time in microseconds")]) -> None:
    """Set sweep time in microseconds."""
    _call("sweep", "set_time", us=us)
    typer.echo(f"sweep time = {us} us")


@sweep_app.command(name="pause")
def sweep_pause() -> None:
    """Pause the sweep."""
    _call("sweep", "pause")
    typer.echo("paused")


@sweep_app.command(name="resume")
def sweep_resume() -> None:
    """Resume the sweep."""
    _call("sweep", "resume")
    typer.echo("resumed")


# -- marker ----------------------------------------------------------------


marker_app = typer.Typer(no_args_is_help=True)
app.add_typer(marker_app, name="marker", help="Marker control")


@marker_app.command(name="get")
def marker_get(
    marker_id: Annotated[
        Optional[int],
        typer.Option("--marker", "-m", help="Marker ID (default: all markers)"),
    ] = None,
) -> None:
    """Print marker data."""
    if marker_id is not None:
        typer.echo(_call("marker", "get", id=marker_id))
    else:
        typer.echo(_call("marker", "get_all"))


@marker_app.command(name="on")
def marker_on(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Enable a marker."""
    _call("marker", "enable", id=marker_id)
    typer.echo(f"marker {marker_id} enabled")


@marker_app.command(name="off")
def marker_off(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Disable a marker."""
    _call("marker", "disable", id=marker_id)
    typer.echo(f"marker {marker_id} disabled")


@marker_app.command(name="freq")
def marker_freq(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
    hz: Annotated[str, typer.Argument(help="Frequency (e.g. 433.92mhz)")],
) -> None:
    """Set marker frequency."""
    _call("marker", "set_freq", id=marker_id, hz=_freq(hz))
    typer.echo(f"marker {marker_id} -> {hz}")


@marker_app.command(name="trace")
def marker_trace(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
    trace_id: Annotated[int, typer.Argument(help="Trace ID")],
) -> None:
    """Assign marker to a trace."""
    _call("marker", "set_trace", id=marker_id, trace_id=trace_id)
    typer.echo(f"marker {marker_id} -> trace {trace_id}")


@marker_app.command(name="peak")
def marker_peak(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Move marker to the highest peak."""
    _call("marker", "move_to_peak", id=marker_id)
    typer.echo(f"marker {marker_id} -> peak")


@marker_app.command(name="delta")
def marker_delta(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
    ref_id: Annotated[int, typer.Argument(help="Reference marker ID")],
) -> None:
    """Set marker as delta from a reference marker."""
    _call("marker", "enable_delta", id=marker_id, ref_id=ref_id)
    typer.echo(f"marker {marker_id} delta from {ref_id}")


@marker_app.command(name="delta-off")
def marker_delta_off(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Disable delta mode on a marker."""
    _call("marker", "disable_delta", id=marker_id)
    typer.echo(f"marker {marker_id} delta off")


@marker_app.command(name="track")
def marker_track(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Enable peak tracking on a marker."""
    _call("marker", "enable_tracking", id=marker_id)
    typer.echo(f"marker {marker_id} tracking on")


@marker_app.command(name="track-off")
def marker_track_off(
    marker_id: Annotated[int, typer.Argument(help="Marker ID")],
) -> None:
    """Disable peak tracking on a marker."""
    _call("marker", "disable_tracking", id=marker_id)
    typer.echo(f"marker {marker_id} tracking off")


# -- trace -----------------------------------------------------------------


trace_app = typer.Typer(no_args_is_help=True)
app.add_typer(trace_app, name="trace", help="Trace control and data")


@trace_app.command(name="get")
def trace_get(
    trace_id: Annotated[
        Optional[int],
        typer.Option("--trace", "-t", help="Trace ID (default: all traces)"),
    ] = None,
) -> None:
    """Print trace settings."""
    if trace_id is not None:
        typer.echo(_call("trace", "get", id=trace_id))
    else:
        typer.echo(_call("trace", "get_all"))


@trace_app.command(name="on")
def trace_on(
    trace_id: Annotated[int, typer.Argument(help="Trace ID")],
) -> None:
    """Enable a trace."""
    _call("trace", "enable", id=trace_id)
    typer.echo(f"trace {trace_id} enabled")


@trace_app.command(name="off")
def trace_off(
    trace_id: Annotated[int, typer.Argument(help="Trace ID")],
) -> None:
    """Disable a trace."""
    _call("trace", "disable", id=trace_id)
    typer.echo(f"trace {trace_id} disabled")


@trace_app.command(name="calc")
def trace_calc(
    trace_id: Annotated[int, typer.Argument(help="Trace ID")],
    calc_type: Annotated[
        _CalcType,
        typer.Argument(help="Calculation type"),
    ],
) -> None:
    """Enable a calculation mode (minh, maxh, maxd, aver4, aver16, aver, quasi)."""
    _call("trace", "enable_calc", id=trace_id, calc=calc_type)
    typer.echo(f"trace {trace_id} calc = {calc_type}")


@trace_app.command(name="calc-off")
def trace_calc_off(
    trace_id: Annotated[int, typer.Argument(help="Trace ID")],
) -> None:
    """Disable calculation on a trace."""
    _call("trace", "disable_calc", id=trace_id)
    typer.echo(f"trace {trace_id} calc off")


@trace_app.command(name="unit")
def trace_unit(
    unit: Annotated[
        _UnitType,
        typer.Argument(help="Display unit"),
    ],
) -> None:
    """Set the trace display unit."""
    _call("trace", "set_unit", unit=unit)
    typer.echo(f"unit = {unit}")


@trace_app.command(name="ref")
def trace_ref(
    dbm: Annotated[float, typer.Argument(help="Reference level in dBm")],
) -> None:
    """Set the trace reference level."""
    _call("trace", "set_ref_level", dbm=dbm)
    typer.echo(f"ref level = {dbm} dBm")


@trace_app.command(name="ref-auto")
def trace_ref_auto() -> None:
    """Set reference level to automatic."""
    _call("trace", "set_ref_level_auto")
    typer.echo("ref level = auto")


@trace_app.command(name="scale")
def trace_scale(
    level: Annotated[float, typer.Argument(help="Scale in dB per division")],
) -> None:
    """Set the trace scale."""
    _call("trace", "set_scale", level=level)
    typer.echo(f"scale = {level} dB/div")


@trace_app.command(name="save")
def trace_save(
    trace_ids: Annotated[
        str, typer.Option("--trace", "-t", help="Comma-separated trace IDs (e.g. 1,2)")
    ],
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file path")
    ] = None,
) -> None:
    """Save trace data as CSV."""
    try:
        ids = [int(s.strip()) for s in trace_ids.split(",") if s.strip()]
    except ValueError as exc:
        _die(f"invalid trace ID in {trace_ids!r}: {exc}")
    if not ids:
        _die("at least one trace ID is required")

    data = _call("trace", "fetch_data", ids=ids)
    freqs = data["frequencies"]
    traces = data["traces"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    if len(ids) == 1:
        writer.writerow(["trace", "point", "frequency", "value"])
        tid = ids[0]
        tkey = str(tid)
        for i, (f, v) in enumerate(zip(freqs, traces[tkey])):
            writer.writerow([tid, i, f, v])
    else:
        headers = ["point", "frequency"] + [f"value_t{t}" for t in ids]
        writer.writerow(headers)
        for i, f in enumerate(freqs):
            row: list[object] = [i, f]
            for tid in ids:
                row.append(traces[str(tid)][i])
            writer.writerow(row)

    csv_text = buf.getvalue()
    if output:
        Path(output).write_text(csv_text)
        typer.echo(f"saved to {output}")
    else:
        typer.echo(csv_text, nl=False)


@trace_app.command(name="stats")
def trace_stats(
    trace_id: Annotated[int, typer.Option("--trace", "-t", help="Trace ID")],
    start: Annotated[str, typer.Option("--start", help="Start frequency (e.g. 410.5mhz)")],
    stop: Annotated[str, typer.Option("--stop", help="Stop frequency (e.g. 600mhz)")],
    unit: Annotated[
        _UnitType,
        typer.Option("--unit", "-u", help="Display unit"),
    ] = "dBm",
    antenna_factor: Annotated[
        Optional[float],
        typer.Option(
            "--antenna-factor",
            "-af",
            help="Antenna factor in dB/m, to report field strength in dBuV/m",
        ),
    ] = None,
) -> None:
    """Compute statistics over a frequency sub-range."""
    start_hz = _freq(start)
    stop_hz = _freq(stop)

    data = _call("trace", "fetch_data", ids=[trace_id])
    freqs = data["frequencies"]
    vals = data["traces"][str(trace_id)]

    try:
        result = compute_stats(freqs, vals, unit, start_hz, stop_hz, antenna_factor)
    except ValueError as exc:
        _die(str(exc))
    n = sum(1 for f in freqs if start_hz <= f <= stop_hz)

    typer.echo(f"Trace {trace_id} stats ({start} - {stop}, {n} points), unit: {unit}")
    typer.echo(f"  {'Channel power':<15s}: {result.channel_power:.1f} {unit}")
    if result.field_strength_dbuvm is not None:
        typer.echo(f"  {'Field strength':<15s}: {result.field_strength_dbuvm:.1f} dBuV/m")
    typer.echo(f"  {'Occupied BW':<15s}: {_fmt_hz(result.occupied_bandwidth_hz)} (99% power)")
    typer.echo(f"  {'Average power':<15s}: {result.average:.1f} {unit}")
    typer.echo(f"  {'Median':<15s}: {result.median:.1f} {unit}")
    typer.echo(f"  {'Min':<15s}: {result.minimum:.1f} {unit}  @ {_fmt_hz(result.min_freq)}")
    typer.echo(f"  {'Max':<15s}: {result.maximum:.1f} {unit}  @ {_fmt_hz(result.max_freq)}")
    typer.echo(f"  {'PAPR':<15s}: {result.papr_db:.1f} dB")
    typer.echo(f"  {'Flatness':<15s}: {result.flatness_db:.1f} dB")


# -- signal ----------------------------------------------------------------


signal_app = typer.Typer(no_args_is_help=True)
app.add_typer(signal_app, name="signal", help="Signal processing")


@signal_app.command(name="spur")
def signal_spur(
    mode: Annotated[
        SpurMode,
        typer.Argument(help="Spur suppression mode"),
    ],
) -> None:
    """Control spur suppression (on, off, or auto)."""
    ops = {"on": "enable_spur", "off": "disable_spur", "auto": "enable_auto_spur"}
    _call("signal", ops[mode])
    typer.echo(f"spur = {mode}")


@signal_app.command(name="lna")
def signal_lna(
    mode: Annotated[
        LnaMode,
        typer.Argument(help="LNA mode"),
    ],
) -> None:
    """Control LNA (on or off)."""
    ops = {"on": "enable_lna", "off": "disable_lna"}
    _call("signal", ops[mode])
    typer.echo(f"lna = {mode}")


# -- menu ------------------------------------------------------------------


menu_app = typer.Typer(no_args_is_help=True)
app.add_typer(menu_app, name="menu", help="Menu navigation")


@menu_app.command(name="trigger")
def menu_trigger(
    ids: Annotated[list[int], typer.Argument(help="Menu path IDs")],
) -> None:
    """Trigger a menu path by its numeric IDs."""
    if not ids:
        _die("at least one menu ID is required")
    _call("menu", "trigger", ids=ids)
    typer.echo(f"menu {' '.join(str(i) for i in ids)}")


# -- preset ----------------------------------------------------------------


preset_app = typer.Typer(no_args_is_help=True)
app.add_typer(preset_app, name="preset", help="Preset save and load")


@preset_app.command(name="load")
def preset_load(
    preset_id: Annotated[int, typer.Argument(help="Preset slot ID")],
) -> None:
    """Load a preset from the device."""
    _call("preset", "load", id=preset_id)
    typer.echo(f"loaded preset {preset_id}")


@preset_app.command(name="save")
def preset_save(
    preset_id: Annotated[int, typer.Argument(help="Preset slot ID")],
) -> None:
    """Save current settings as a preset on the device."""
    _call("preset", "save", id=preset_id)
    typer.echo(f"saved preset {preset_id}")


# -- capture ---------------------------------------------------------------


capture_app = typer.Typer(no_args_is_help=True)
app.add_typer(capture_app, name="capture", help="Screenshot capture")


@capture_app.command(name="save")
def capture_save(
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file path")
    ] = None,
) -> None:
    """Fetch a screenshot and save it as a PNG file."""
    png = _call("capture", "fetch")
    path = output or f"SA_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
    Path(path).write_bytes(png)
    typer.echo(f"saved to {path}")


# -- raw -------------------------------------------------------------------


raw_app = typer.Typer(no_args_is_help=True)
app.add_typer(raw_app, name="raw", help="Raw passthrough commands")


@raw_app.command(name="execute")
def raw_execute(
    command: Annotated[str, typer.Argument(help="Raw command to send to the device")],
) -> None:
    """Send a raw command to the device and print the response."""
    typer.echo(_call("raw", "execute", command=command))


# -- session ---------------------------------------------------------------


session_app = typer.Typer(no_args_is_help=True)
app.add_typer(session_app, name="session", help="Session management")


@session_app.command(name="list")
def session_list() -> None:
    """List active sessions on the hub."""
    sessions = _call("session", "list")
    if not sessions:
        typer.echo("no active sessions")
        return
    for s in sessions:
        transport = s.get("transport", "?")
        peer = s.get("peer", "?")
        device = s.get("selected_device") or "-"
        uptime = s.get("uptime_seconds", 0)
        typer.echo(f"{transport:<6s} {peer:<24s} device={device:<16s} uptime={uptime:.0f}s")


@session_app.command(name="status")
def session_status() -> None:
    """Print the current session status."""
    s = _call("session", "status")
    if s["active"]:
        typer.echo(
            f"active  peer={s['peer']}  device={s.get('selected_device')}  uptime={s['uptime_seconds']}s"
        )
    else:
        typer.echo("inactive")


@session_app.command(name="disconnect")
def session_disconnect() -> None:
    """Disconnect the current session."""
    _call("session", "disconnect")
    typer.echo("disconnected")


@session_app.command(name="force-takeover")
def session_force_takeover() -> None:
    """Allow another controller to take over this session."""
    _call("session", "force_takeover")
    typer.echo("takeover allowed")


# -- helpers ---------------------------------------------------------------


def _fmt_hz(hz: int) -> str:
    if hz >= 1_000_000_000:
        whole = hz // 1_000_000_000
        frac = hz % 1_000_000_000
        if frac == 0:
            return f"{whole} GHz"
        return f"{whole}.{frac:09d}".rstrip("0") + " GHz"
    if hz >= 1_000_000:
        whole = hz // 1_000_000
        frac = hz % 1_000_000
        if frac == 0:
            return f"{whole} MHz"
        return f"{whole}.{frac:06d}".rstrip("0") + " MHz"
    if hz >= 1_000:
        whole = hz // 1_000
        frac = hz % 1_000
        if frac == 0:
            return f"{whole} kHz"
        return f"{whole}.{frac:03d}".rstrip("0") + " kHz"
    return f"{hz} Hz"


def main() -> None:
    """Entry point for the tsanet-ctl console script."""
    app()


if __name__ == "__main__":
    main()
