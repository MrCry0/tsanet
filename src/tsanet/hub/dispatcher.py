"""RPC dispatcher that routes incoming requests to device commands (brief 5, 11.5).

Maps the RPC domain API (brief section 5) to the device command functions in
:mod:`tsanet.device.commands`. Session and device management RPCs are handled
directly against the registry and session manager.
"""

from __future__ import annotations

from __future__ import annotations

from typing import TYPE_CHECKING

from tsanet.common.errors import DispatchError, SessionError
from tsanet.device.commands import capture as cmd_capture
from tsanet.device.commands import device as cmd_device
from tsanet.device.commands import marker as cmd_marker
from tsanet.device.commands import menu as cmd_menu
from tsanet.device.commands import preset as cmd_preset
from tsanet.device.commands import raw as cmd_raw
from tsanet.device.commands import signal as cmd_signal
from tsanet.device.commands import sweep as cmd_sweep
from tsanet.device.commands import trace as cmd_trace
from tsanet.device.model import FRAMEBUFFER
from tsanet.device.parsing import parse_frequencies, parse_trace_values
from tsanet.device.png import encode_png
from tsanet.device.rgb565 import decode_rgb565
from tsanet.device.transport import TinySA
from tsanet.hub.registry import DeviceRegistry
from tsanet.hub.session import SessionManager
from tsanet.protocol.messages import Request, Response, Status
from tsanet.protocol.transport import Connection

if TYPE_CHECKING:
    from tsanet.hub.subscriptions import SubscriptionManager


class Dispatcher:
    """Routes incoming RPC requests to device commands and hub services."""

    def __init__(
        self,
        registry: DeviceRegistry,
        sessions: SessionManager,
        subscriptions: SubscriptionManager | None = None,
    ) -> None:
        self._registry = registry
        self._sessions = sessions
        self._subscriptions = subscriptions

    # -- public API --------------------------------------------------------

    def dispatch(self, request: Request, connection: Connection) -> Response:
        try:
            data = self._route(request, connection)
            return Response(id=request.id, status=Status.OK, data=data)
        except Exception as exc:
            return Response(id=request.id, status=Status.ERROR, error=str(exc))

    # -- top-level routing -------------------------------------------------

    def _route(self, request: Request, connection: Connection):
        domain = request.domain
        op = request.op
        args = request.args

        if domain == "devices":
            return self._handle_devices(op, args)
        if domain == "session":
            return self._handle_session(op, args, connection)

        # Validate the domain before resolving the device so that unknown
        # domains produce a clear DispatchError instead of a misleading
        # "no device selected" error.
        if domain == "capture":
            tx = self._resolve_device()
            return self._handle_capture(tx, op, args)

        if domain == "trace" and op in ("subscribe", "unsubscribe"):
            if self._subscriptions is None:
                raise DispatchError("subscriptions not configured on this hub")
            return self._handle_trace_subscription(op, args)

        handler = _HANDLERS.get(domain)
        if handler is None:
            raise DispatchError(f"unknown domain: {domain!r}")

        tx = self._resolve_device()
        return handler(tx, op, args)

    def _resolve_device(self) -> TinySA:
        session = self._sessions.current
        if session is None:
            raise SessionError("no active session")
        device_id = session.selected_device_id
        if device_id is None:
            raise DispatchError("no device selected; use devices.select first")
        return self._registry.get(device_id).transport

    # -- devices domain ----------------------------------------------------

    def _handle_devices(self, op: str, args: dict):
        if op == "list":
            return [
                {
                    "device_id": d.device_id,
                    "port": d.port,
                    "model": d.info.model_string,
                    "firmware": d.info.firmware,
                    "hardware": d.info.hardware,
                    "busy": d.busy,
                }
                for d in self._registry.list()
            ]
        if op == "select":
            device_id = args.get("device_id")
            if not device_id:
                raise DispatchError("device_id is required for devices.select")
            self._registry.get(device_id)
            self._sessions.select_device(device_id)
            return {"selected": device_id}
        raise DispatchError(f"unknown devices op: {op!r}")

    # -- session domain ----------------------------------------------------

    def _handle_session(self, op: str, args: dict, connection: Connection):
        if op == "status":
            return self._sessions.status()
        if op == "list":
            return self._sessions.list_sessions()
        if op == "disconnect":
            self._sessions.disconnect()
            return {"active": False}
        if op == "force_takeover":
            self._sessions.allow_takeover()
            return {"active": True}
        raise DispatchError(f"unknown session op: {op!r}")

    # -- capture domain (instance method — needs model from registry) ------

    def _handle_capture(self, tx: TinySA, op: str, args: dict):
        if op == "fetch":
            session = self._sessions.current
            assert session is not None
            device = self._registry.get(session.selected_device_id)  # type: ignore[arg-type]
            model = device.info.model
            width, height = FRAMEBUFFER[model]
            raw_fb = cmd_capture.fetch_framebuffer(tx, model)
            rgba = decode_rgb565(raw_fb, width, height)
            return encode_png(rgba, width, height)
        raise DispatchError(f"unknown capture op: {op!r}")

    # -- trace subscription (instance method — delegates to Manager) -----

    def _handle_trace_subscription(self, op: str, args: dict):
        assert self._subscriptions is not None
        if op == "subscribe":
            return self._subscriptions.subscribe(args["ids"], args.get("interval"))
        if op == "unsubscribe":
            return self._subscriptions.unsubscribe()
        raise DispatchError(f"unknown trace subscription op: {op!r}")


# -- per-domain handler functions ------------------------------------------
# Plain functions receiving a TinySA transport; the Dispatcher resolves the
# active device before invoking them.  The capture domain is handled inside
# the Dispatcher class itself (it needs model info from the registry).


def _device(tx: TinySA, op: str, args: dict):
    if op == "get_version":
        return cmd_device.get_version(tx)
    if op == "get_id":
        return cmd_device.get_id(tx)
    if op == "set_id":
        return cmd_device.set_id(tx, args["id"])
    if op == "get_battery":
        return cmd_device.get_battery(tx)
    if op == "get_battery_offset":
        return cmd_device.get_battery_offset(tx)
    if op == "set_battery_offset":
        return cmd_device.set_battery_offset(tx, args["v"])
    if op == "reset":
        cmd_device.reset(tx, dfu=args.get("dfu", False))
        return None
    raise DispatchError(f"unknown device op: {op!r}")


# Frequency above which the Ultra model needs LNA enabled (high-band mode).
_LNA_THRESHOLD_HZ = 800_000_000


def _ensure_lna_for_hz(tx: TinySA, hz: int) -> None:
    """Enable LNA if *hz* exceeds the low-band threshold."""
    if hz > _LNA_THRESHOLD_HZ:
        cmd_signal.enable_lna(tx)


def _sweep(tx: TinySA, op: str, args: dict):
    if op == "get":
        return cmd_sweep.get(tx)
    if op == "get_status":
        return cmd_sweep.get_status(tx)
    if op == "set_mode":
        return cmd_sweep.set_mode(tx, args["mode"])
    if op == "set_start":
        _ensure_lna_for_hz(tx, args["hz"])
        return cmd_sweep.set_start(tx, args["hz"])
    if op == "set_stop":
        _ensure_lna_for_hz(tx, args["hz"])
        return cmd_sweep.set_stop(tx, args["hz"])
    if op == "set_center":
        _ensure_lna_for_hz(tx, args["hz"])
        return cmd_sweep.set_center(tx, args["hz"])
    if op == "set_span":
        return cmd_sweep.set_span(tx, args["hz"])
    if op == "set_cw":
        _ensure_lna_for_hz(tx, args["hz"])
        return cmd_sweep.set_cw(tx, args["hz"])
    if op == "set_start_stop":
        _ensure_lna_for_hz(tx, max(args["start"], args.get("stop", 0)))
        return cmd_sweep.set_start_stop(tx, args["start"], args["stop"], args.get("points"))
    if op == "set_time":
        return cmd_sweep.set_time(tx, args["us"])
    if op == "pause":
        return cmd_sweep.pause(tx)
    if op == "resume":
        return cmd_sweep.resume(tx)
    raise DispatchError(f"unknown sweep op: {op!r}")


def _marker(tx: TinySA, op: str, args: dict):
    if op == "get":
        return cmd_marker.get(tx, args["id"])
    if op == "get_all":
        return cmd_marker.get_all(tx)
    if op == "enable":
        return cmd_marker.enable(tx, args["id"])
    if op == "disable":
        return cmd_marker.disable(tx, args["id"])
    if op == "set_freq":
        return cmd_marker.set_freq(tx, args["id"], args["hz"])
    if op == "set_trace":
        return cmd_marker.set_trace(tx, args["id"], args["trace_id"])
    if op == "move_to_peak":
        return cmd_marker.move_to_peak(tx, args["id"])
    if op == "enable_delta":
        return cmd_marker.enable_delta(tx, args["id"], args["ref_id"])
    if op == "disable_delta":
        return cmd_marker.disable_delta(tx, args["id"])
    if op == "enable_tracking":
        return cmd_marker.enable_tracking(tx, args["id"])
    if op == "disable_tracking":
        return cmd_marker.disable_tracking(tx, args["id"])
    raise DispatchError(f"unknown marker op: {op!r}")


def _trace(tx: TinySA, op: str, args: dict):
    if op == "get":
        return cmd_trace.get(tx, args["id"])
    if op == "get_all":
        return cmd_trace.get_all(tx)
    if op == "get_frequencies":
        return cmd_trace.get_frequencies(tx)
    if op == "fetch_data":
        freq_text = cmd_trace.get_frequencies(tx)
        frequencies = parse_frequencies(freq_text)
        traces: dict[str, list[float]] = {}
        for tid in args["ids"]:
            traces[str(tid)] = parse_trace_values(cmd_trace.fetch_value(tx, tid))
        return {"frequencies": frequencies, "traces": traces}
    if op == "enable":
        return cmd_trace.enable(tx, args["id"])
    if op == "disable":
        return cmd_trace.disable(tx, args["id"])
    if op == "enable_calc":
        return cmd_trace.enable_calc(tx, args["id"], args["calc"])
    if op == "disable_calc":
        return cmd_trace.disable_calc(tx, args["id"])
    if op == "set_unit":
        return cmd_trace.set_unit(tx, args["unit"])
    if op == "set_ref_level":
        return cmd_trace.set_ref_level(tx, args["dbm"])
    if op == "set_ref_level_auto":
        return cmd_trace.set_ref_level_auto(tx)
    if op == "set_scale":
        return cmd_trace.set_scale(tx, args["level"])
    raise DispatchError(f"unknown trace op: {op!r}")


def _signal(tx: TinySA, op: str, args: dict):
    if op == "enable_spur":
        return cmd_signal.enable_spur(tx)
    if op == "disable_spur":
        return cmd_signal.disable_spur(tx)
    if op == "enable_auto_spur":
        return cmd_signal.enable_auto_spur(tx)
    if op == "enable_lna":
        return cmd_signal.enable_lna(tx)
    if op == "disable_lna":
        return cmd_signal.disable_lna(tx)
    raise DispatchError(f"unknown signal op: {op!r}")


def _menu(tx: TinySA, op: str, args: dict):
    if op == "trigger":
        return cmd_menu.trigger(tx, args["ids"])
    raise DispatchError(f"unknown menu op: {op!r}")


def _preset(tx: TinySA, op: str, args: dict):
    if op == "load":
        return cmd_preset.load(tx, args["id"])
    if op == "save":
        return cmd_preset.save(tx, args["id"])
    raise DispatchError(f"unknown preset op: {op!r}")


def _raw(tx: TinySA, op: str, args: dict):
    if op == "execute":
        return cmd_raw.execute(tx, args["command"])
    raise DispatchError(f"unknown raw op: {op!r}")


_HANDLERS = {
    "device": _device,
    "sweep": _sweep,
    "marker": _marker,
    "trace": _trace,
    "signal": _signal,
    "menu": _menu,
    "preset": _preset,
    "raw": _raw,
}
