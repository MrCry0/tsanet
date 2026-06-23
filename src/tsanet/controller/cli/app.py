"""``tsanet-ctl`` entry point (brief 9, 11.6).

Typer-based CLI with command groups matching the RPC domains.
"""

from __future__ import annotations

import csv
import datetime
import io
from pathlib import Path
from typing import Annotated, Optional

import typer

from tsanet.common.config import NetworkConfig
from tsanet.controller.config import DEFAULT_CONFIG_PATH, ControllerConfig
from tsanet.controller.parse import parse_frequency
from tsanet.controller.rpc_client import RpcClient, RpcError
from tsanet.controller.stats import compute_stats
from tsanet.device.model import VALID_CALC, VALID_UNITS

app = typer.Typer(no_args_is_help=True)
_client: RpcClient | None = None


def _rpc() -> RpcClient:
    if _client is None:
        raise typer.Exit("not connected; check --config or connection flags")
    return _client


def _call(domain: str, op: str, **args: object) -> object:
    try:
        return _rpc().call(domain, op, **args)
    except RpcError as exc:
        raise typer.Exit(str(exc)) from exc


def _die(msg: str) -> typer.Exit:
    raise typer.Exit(msg)


# -- callback --------------------------------------------------------------


@app.callback()
def _setup(
    config_path: Annotated[
        Optional[str],
        typer.Option("--config", "-c", help="Path to controller config YAML"),
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
) -> None:
    global _client
    config = ControllerConfig.load(config_path or DEFAULT_CONFIG_PATH)
    if mode is not None:
        config.network.mode = mode  # type: ignore[assignment]
    if transport is not None:
        config.network.transport = transport  # type: ignore[assignment]
    if address is not None:
        config.network.address = address
    if port is not None:
        config.network.port = port
    NetworkConfig.model_validate(config.network.__dict__)
    _client = RpcClient(config)
    _client.connect()


# -- devices ---------------------------------------------------------------


devices_app = typer.Typer(no_args_is_help=True)
app.add_typer(devices_app, name="devices", help="Device discovery and selection")


@devices_app.command(name="list")
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


@devices_app.command(name="select")
def devices_select(
    device_id: Annotated[str, typer.Argument(help="Device ID to select")],
) -> None:
    """Select a device for subsequent commands."""
    _call("devices", "select", device_id=device_id)
    typer.echo(f"selected {device_id}")


# -- device ----------------------------------------------------------------


device_app = typer.Typer(no_args_is_help=True)
app.add_typer(device_app, name="device", help="Device identification and control")


@device_app.command(name="version")
def device_version() -> None:
    """Print device firmware and hardware version."""
    typer.echo(_call("device", "get_version"))


@device_app.command(name="id")
def device_id(
    set_id: Annotated[Optional[int], typer.Option("--set", help="Assign a new device ID")] = None,
) -> None:
    """Get or set the device ID."""
    if set_id is not None:
        _call("device", "set_id", id=set_id)
        typer.echo(f"device ID set to {set_id}")
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


@sweep_app.command(name="get")
def sweep_get() -> None:
    """Print current sweep settings."""
    typer.echo(_call("sweep", "get"))


@sweep_app.command(name="status")
def sweep_status() -> None:
    """Print sweep status."""
    typer.echo(_call("sweep", "get_status"))


@sweep_app.command(name="start")
def sweep_start(hz: Annotated[str, typer.Argument(help="Start frequency (e.g. 100mhz)")]) -> None:
    """Set sweep start frequency."""
    _call("sweep", "set_start", hz=parse_frequency(hz))
    typer.echo(f"start = {hz}")


@sweep_app.command(name="stop")
def sweep_stop(hz: Annotated[str, typer.Argument(help="Stop frequency")]) -> None:
    """Set sweep stop frequency."""
    _call("sweep", "set_stop", hz=parse_frequency(hz))
    typer.echo(f"stop = {hz}")


@sweep_app.command(name="center")
def sweep_center(hz: Annotated[str, typer.Argument(help="Center frequency")]) -> None:
    """Set sweep center frequency."""
    _call("sweep", "set_center", hz=parse_frequency(hz))
    typer.echo(f"center = {hz}")


@sweep_app.command(name="span")
def sweep_span(hz: Annotated[str, typer.Argument(help="Span")]) -> None:
    """Set sweep span."""
    _call("sweep", "set_span", hz=parse_frequency(hz))
    typer.echo(f"span = {hz}")


@sweep_app.command(name="cw")
def sweep_cw(hz: Annotated[str, typer.Argument(help="CW frequency")]) -> None:
    """Set sweep to continuous-wave mode at a frequency."""
    _call("sweep", "set_cw", hz=parse_frequency(hz))
    typer.echo(f"cw = {hz}")


@sweep_app.command(name="range")
def sweep_range(
    start: Annotated[str, typer.Argument(help="Start frequency")],
    stop: Annotated[str, typer.Argument(help="Stop frequency")],
    points: Annotated[Optional[int], typer.Option("--points", "-p", help="Number of points")] = None,
) -> None:
    """Set sweep start, stop, and optionally point count."""
    _call("sweep", "set_start_stop", start=parse_frequency(start), stop=parse_frequency(stop), points=points)
    typer.echo(f"range = {start} - {stop}" + (f" ({points} pts)" if points else ""))


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
    marker_id: Annotated[Optional[int], typer.Option("--id", "-m", help="Marker ID (default: all)")] = None,
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
    hz: Annotated[str, typer.Argument(help="Frequency")],
) -> None:
    """Set marker frequency."""
    _call("marker", "set_freq", id=marker_id, hz=parse_frequency(hz))
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
    trace_id: Annotated[Optional[int], typer.Option("--id", "-t", help="Trace ID (default: all)")] = None,
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
    calc_type: Annotated[str, typer.Argument(help=f"Calculation type: {', '.join(sorted(VALID_CALC))}")],
) -> None:
    """Enable a calculation (minh, maxh, maxd, aver4, aver16, aver, quasi)."""
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
    unit: Annotated[str, typer.Argument(help=f"Unit: {', '.join(sorted(VALID_UNITS))}")],
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
    trace_ids: Annotated[str, typer.Option("--trace", "-t", help="Comma-separated trace IDs (e.g. 1,2)")],
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file path")
    ] = None,
) -> None:
    """Save trace data as CSV."""
    ids = [int(s.strip()) for s in trace_ids.split(",") if s.strip()]
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
        for i, (f, v) in enumerate(zip(freqs, traces[tid])):
            writer.writerow([tid, i, f, v])
    else:
        headers = ["point", "frequency"] + [f"value_t{t}" for t in ids]
        writer.writerow(headers)
        for i, f in enumerate(freqs):
            row: list[object] = [i, f]
            for tid in ids:
                row.append(traces[tid][i])
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
    stop: Annotated[str, typer.Option("--stop", help="Stop frequency")],
    unit: Annotated[str, typer.Option("--unit", "-u", help="Trace unit (dBm, dBmV, ...)")] = "dBm",
) -> None:
    """Compute statistics over a frequency sub-range."""
    start_hz = parse_frequency(start)
    stop_hz = parse_frequency(stop)

    data = _call("trace", "fetch_data", ids=[trace_id])
    freqs = data["frequencies"]
    vals = data["traces"][trace_id]

    result = compute_stats(freqs, vals, unit, start_hz, stop_hz)
    n = sum(1 for f in freqs if start_hz <= f <= stop_hz)

    typer.echo(
        f"Trace {trace_id} stats ({start} - {stop}, {n} points), unit: {unit}"
    )
    typer.echo(f"  Average power : {result.average:.1f} {unit}")
    typer.echo(f"  Median        : {result.median:.1f} {unit}")
    typer.echo(f"  Min           : {result.minimum:.1f} {unit}  @ {_fmt_hz(result.min_freq)}")
    typer.echo(f"  Max           : {result.maximum:.1f} {unit}  @ {_fmt_hz(result.max_freq)}")


# -- signal ----------------------------------------------------------------


signal_app = typer.Typer(no_args_is_help=True)
app.add_typer(signal_app, name="signal", help="Signal processing")


@signal_app.command(name="spur")
def signal_spur(
    mode: Annotated[str, typer.Argument(help="on, off, or auto")],
) -> None:
    """Control spur suppression."""
    if mode == "on":
        _call("signal", "enable_spur")
    elif mode == "off":
        _call("signal", "disable_spur")
    elif mode == "auto":
        _call("signal", "enable_auto_spur")
    else:
        _die("mode must be on, off, or auto")
    typer.echo(f"spur = {mode}")


@signal_app.command(name="lna")
def signal_lna(
    mode: Annotated[str, typer.Argument(help="on or off")],
) -> None:
    """Control LNA."""
    if mode == "on":
        _call("signal", "enable_lna")
    elif mode == "off":
        _call("signal", "disable_lna")
    else:
        _die("mode must be on or off")
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
        typer.echo(f"active  peer={s['peer']}  device={s.get('selected_device')}  uptime={s['uptime_seconds']}s")
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
        return f"{hz / 1_000_000_000:.2f} GHz"
    if hz >= 1_000_000:
        return f"{hz / 1_000_000:.2f} MHz"
    if hz >= 1_000:
        return f"{hz / 1_000:.2f} kHz"
    return f"{hz} Hz"


def main() -> None:
    """Entry point for the tsanet-ctl console script."""
    app()


if __name__ == "__main__":
    main()
