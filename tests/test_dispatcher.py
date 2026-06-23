"""Tests for the RPC dispatcher."""

from __future__ import annotations

from fakeserial import FakeDevicePort, FakeSerial

from tsanet.device.model import FRAMEBUFFER, Model
from tsanet.device.transport import TinySA
from tsanet.hub.dispatcher import Dispatcher
from tsanet.hub.registry import DeviceRegistry
from tsanet.hub.session import SessionManager
from tsanet.protocol.messages import Request, Status


class DummyConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _make_registry():
    opener = _FakeOpener({"/dev/ultra": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    registry = DeviceRegistry(lambda: ["/dev/ultra"], opener, probe_attempts=1)
    registry.scan()
    return registry, opener


class _FakeOpener:
    def __init__(self, devices: dict[str, bytes | None]) -> None:
        self._devices = devices
        self._handles: dict[str, FakeDevicePort] = {}

    def __call__(self, name: str) -> FakeDevicePort:
        port = FakeDevicePort(body=self._devices[name])
        self._handles[name] = port
        return port


def _replace_transport(registry: DeviceRegistry, device_id: str, tx: TinySA) -> TinySA:
    device = registry.get(device_id)
    device.transport = tx
    return tx


# ----------------------------------------------------------------------


def _make_dispatcher():
    registry, _ = _make_registry()
    sessions = SessionManager()
    conn = DummyConnection()
    sessions.admit(conn, peer="test")
    sessions.select_device("/dev/ultra")
    dispatcher = Dispatcher(registry, sessions)
    return dispatcher, registry, sessions, conn


def _dispatch(dispatcher, conn, domain, op, **args):
    req = Request(id=1, domain=domain, op=op, args=args)
    return dispatcher.dispatch(req, conn)


def _ok(response):
    assert response.status == Status.OK, f"expected OK, got error: {response.error}"
    return response.data


def _error(response):
    assert response.status == Status.ERROR
    return response.error


# ======================================================================
# devices domain
# ======================================================================


def test_devices_list_empty():
    opener = _FakeOpener({})
    registry = DeviceRegistry(lambda: [], opener)
    dispatcher = Dispatcher(registry, SessionManager())
    data = _ok(_dispatch(dispatcher, DummyConnection(), "devices", "list"))
    assert data == []


def test_devices_list_returns_device_info():
    dispatcher, *_ = _make_dispatcher()
    data = _ok(_dispatch(dispatcher, DummyConnection(), "devices", "list"))
    assert len(data) == 1
    d = data[0]
    assert d["device_id"] == "/dev/ultra"
    assert d["model"] == "tinySA4"
    assert d["firmware"] == "1.4"
    assert d["hardware"] == "0.4.5.1"
    assert d["busy"] is False


def test_devices_select():
    dispatcher, registry, sessions, conn = _make_dispatcher()

    opener = _FakeOpener({"/dev/other": b"tinySA4_v1.4 HW Version:V0.4.5.1"})
    reg2 = DeviceRegistry(lambda: ["/dev/other"], opener, probe_attempts=1)
    reg2.scan()

    dispatcher = Dispatcher(reg2, sessions)
    data = _ok(_dispatch(dispatcher, conn, "devices", "select", device_id="/dev/other"))
    assert data == {"selected": "/dev/other"}
    assert sessions.status()["selected_device"] == "/dev/other"


def test_devices_select_unknown_device():
    dispatcher, *_ = _make_dispatcher()
    err = _error(
        _dispatch(dispatcher, DummyConnection(), "devices", "select", device_id="/dev/nonexistent")
    )
    assert "/dev/nonexistent" in err


def test_devices_select_missing_device_id():
    dispatcher, *_ = _make_dispatcher()
    err = _error(_dispatch(dispatcher, DummyConnection(), "devices", "select"))
    assert "device_id" in err.lower()


def test_devices_unknown_op():
    dispatcher, *_ = _make_dispatcher()
    err = _error(_dispatch(dispatcher, DummyConnection(), "devices", "bogus"))
    assert "unknown devices op" in err.lower()


# ======================================================================
# session domain
# ======================================================================


def test_session_status_active():
    dispatcher, _, sessions, conn = _make_dispatcher()
    data = _ok(_dispatch(dispatcher, conn, "session", "status"))
    assert data["active"] is True
    assert data["peer"] == "test"
    assert data["selected_device"] == "/dev/ultra"


def test_session_status_inactive():
    dispatcher = Dispatcher(DeviceRegistry(lambda: [], lambda n: None), SessionManager())
    data = _ok(_dispatch(dispatcher, DummyConnection(), "session", "status"))
    assert data == {"active": False}


def test_session_disconnect():
    dispatcher, _, sessions, conn = _make_dispatcher()
    data = _ok(_dispatch(dispatcher, conn, "session", "disconnect"))
    assert data == {"active": False}
    assert sessions.current is None


def test_session_force_takeover_enables_next_admission():
    dispatcher, _, sessions, conn = _make_dispatcher()

    other_conn = DummyConnection()
    sessions.admit(other_conn, peer="other", force=True)
    # conn was evicted and closed by the force admit above.
    assert conn.closed is True

    # force_takeover sets the allow_takeover flag via the (now-closed)
    # connection's session.  The next connection will be admitted without
    # needing force.
    data = _ok(_dispatch(dispatcher, conn, "session", "force_takeover"))
    assert data == {"active": True}

    # Now a new connection can take over without force.
    new_conn = DummyConnection()
    sessions.admit(new_conn, peer="new")
    # The incumbent (other_conn) was evicted and closed.
    assert other_conn.closed is True
    assert sessions.current.connection is new_conn


def test_session_force_takeover_sets_allow_flag():
    dispatcher, _, sessions, conn = _make_dispatcher()
    data = _ok(_dispatch(dispatcher, conn, "session", "force_takeover"))
    assert data == {"active": True}
    assert sessions.current.connection is conn

    # After force_takeover, a new connection is admitted without force.
    new_conn = DummyConnection()
    sessions.admit(new_conn, peer="taker")
    assert sessions.current.connection is new_conn


def test_session_unknown_op():
    dispatcher, *_ = _make_dispatcher()
    err = _error(_dispatch(dispatcher, DummyConnection(), "session", "bogus"))
    assert "unknown session op" in err.lower()


# ======================================================================
# device domain
# ======================================================================


def test_device_get_version():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"version\r\ntinySA4_v2.0\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "device", "get_version"))
    assert data == "tinySA4_v2.0"


def test_device_get_id():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"deviceid\r\n42\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "device", "get_id"))
    assert data == "42"


def test_device_set_id():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"deviceid 99\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "device", "set_id", id=99))
    assert data == ""
    assert tx.written == [b"deviceid 99\r"]


def test_device_reset():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "device", "reset"))
    assert data is None
    assert tx.written == [b"reset\r"]


def test_device_reset_dfu():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "device", "reset", dfu=True))
    assert tx.written == [b"reset dfu\r"]


# ======================================================================
# sweep domain
# ======================================================================


def test_sweep_set_start_stop():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"sweep 410500000 600000000\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "sweep", "set_start_stop", start=410500000, stop=600000000))
    assert tx.written == [b"sweep 410500000 600000000\r"]


def test_sweep_set_start_stop_with_points():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"sweep 1 2 101\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "sweep", "set_start_stop", start=1, stop=2, points=101))
    assert tx.written == [b"sweep 1 2 101\r"]


def test_sweep_pause_resume():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"pause\r\nch> ", b"resume\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "sweep", "pause"))
    _ok(_dispatch(dispatcher, conn, "sweep", "resume"))
    assert tx.written == [b"pause\r", b"resume\r"]


# ======================================================================
# marker domain
# ======================================================================


def test_marker_enable_disable():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"marker 2 on\r\nch> ", b"marker 2 off\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "marker", "enable", id=2))
    _ok(_dispatch(dispatcher, conn, "marker", "disable", id=2))
    assert tx.written == [b"marker 2 on\r", b"marker 2 off\r"]


def test_marker_set_freq():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"marker 1 433920000\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "marker", "set_freq", id=1, hz=433920000))
    assert tx.written == [b"marker 1 433920000\r"]


def test_marker_enable_delta_and_tracking():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial(
        [
            b"marker 2 delta 1\r\nch> ",
            b"marker 2 delta off\r\nch> ",
            b"marker 1 tracking on\r\nch> ",
        ]
    )
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "marker", "enable_delta", id=2, ref_id=1))
    _ok(_dispatch(dispatcher, conn, "marker", "disable_delta", id=2))
    _ok(_dispatch(dispatcher, conn, "marker", "enable_tracking", id=1))


def test_marker_get_and_get_all():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"marker 1\r\n1 433000000\r\nch> ", b"marker\r\n1 433000000\r\n2 868000000\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    assert _ok(_dispatch(dispatcher, conn, "marker", "get", id=1)) == "1 433000000"
    assert "2 868000000" in _ok(_dispatch(dispatcher, conn, "marker", "get_all"))


# ======================================================================
# trace domain
# ======================================================================


def test_trace_enable_calc():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"calc 1 minh\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "trace", "enable_calc", id=1, calc="minh"))
    assert tx.written == [b"calc 1 minh\r"]


def test_trace_set_unit():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"trace dBmV\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "trace", "set_unit", unit="dBmV"))
    assert tx.written == [b"trace dBmV\r"]


def test_trace_set_ref_level():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"trace reflevel -20.0\r\nch> ", b"trace reflevel auto\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "trace", "set_ref_level", dbm=-20.0))
    _ok(_dispatch(dispatcher, conn, "trace", "set_ref_level_auto"))
    assert tx.written == [b"trace reflevel -20.0\r", b"trace reflevel auto\r"]


def test_trace_fetch_data():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial(
        [
            b"frequencies\r\n100000000\r\n200000000\r\nch> ",
            b"trace 1 value\r\n-50.5\r\n-51.2\r\nch> ",
            b"trace 2 value\r\n-60.0\r\n-61.5\r\nch> ",
        ]
    )
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "trace", "fetch_data", ids=[1, 2]))
    assert data["frequencies"] == [100000000, 200000000]
    assert data["traces"] == {1: [-50.5, -51.2], 2: [-60.0, -61.5]}


def test_trace_get_frequencies():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"frequencies\r\n100000000\r\n200000000\r\n300000000\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "trace", "get_frequencies"))
    assert "200000000" in data


# ======================================================================
# signal domain
# ======================================================================


def test_signal_lna():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"lna on\r\nch> ", b"lna off\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "signal", "enable_lna"))
    _ok(_dispatch(dispatcher, conn, "signal", "disable_lna"))
    assert tx.written == [b"lna on\r", b"lna off\r"]


def test_signal_spur():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"spur on\r\nch> ", b"spur auto\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "signal", "enable_spur"))
    _ok(_dispatch(dispatcher, conn, "signal", "enable_auto_spur"))


# ======================================================================
# menu, preset, raw domains
# ======================================================================


def test_menu_trigger():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"menu 1 2 3\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "menu", "trigger", ids=[1, 2, 3]))
    assert tx.written == [b"menu 1 2 3\r"]


def test_preset_load_save():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"load 1\r\nch> ", b"save 5\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    _ok(_dispatch(dispatcher, conn, "preset", "load", id=1))
    _ok(_dispatch(dispatcher, conn, "preset", "save", id=5))
    assert tx.written == [b"load 1\r", b"save 5\r"]


def test_raw_execute():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([b"scanraw\r\n100\r\n200\r\nch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "raw", "execute", command="scanraw"))
    assert "200" in data
    assert tx.written == [b"scanraw\r"]


# ======================================================================
# capture domain
# ======================================================================


def test_capture_fetch():
    dispatcher, registry, _, conn = _make_dispatcher()
    model = Model.ULTRA
    width, height = FRAMEBUFFER[model]
    payload = b"\x00\x00" * width * height  # all black, valid RGB565
    tx = FakeSerial([b"capture\r\n" + payload + b"ch> "])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))

    data = _ok(_dispatch(dispatcher, conn, "capture", "fetch"))
    assert isinstance(data, bytes)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


# ======================================================================
# error cases
# ======================================================================


def test_no_session_returns_error():
    registry, _ = _make_registry()
    dispatcher = Dispatcher(registry, SessionManager())
    err = _error(_dispatch(dispatcher, DummyConnection(), "device", "get_version"))
    assert "no active session" in err.lower()


def test_no_device_selected_returns_error():
    registry, _ = _make_registry()
    sessions = SessionManager()
    sessions.admit(DummyConnection())
    dispatcher = Dispatcher(registry, sessions)
    err = _error(_dispatch(dispatcher, DummyConnection(), "device", "get_version"))
    assert "no device selected" in err.lower()


def test_unknown_domain():
    dispatcher, *_ = _make_dispatcher()
    err = _error(_dispatch(dispatcher, DummyConnection(), "nonexistent", "op"))
    assert "unknown domain" in err.lower()


def test_unknown_device_op():
    dispatcher, *_ = _make_dispatcher()
    err = _error(_dispatch(dispatcher, DummyConnection(), "device", "nonexistent"))
    assert "unknown device op" in err.lower()


def test_missing_required_arg():
    dispatcher, registry, _, conn = _make_dispatcher()
    tx = FakeSerial([])
    _replace_transport(registry, "/dev/ultra", TinySA(tx, attempts=1))
    err = _error(_dispatch(dispatcher, conn, "sweep", "set_start"))
    assert err
