"""Tests that each command builder emits the exact wire string from brief 4."""

from __future__ import annotations

import pytest

from tsanet.device.commands import (
    capture,
    device,
    marker,
    menu,
    preset,
    raw,
    signal,
    sweep,
    trace,
)
from tsanet.device.model import Model
from tsanet.device.transport import TinySA
from fakeserial import FakeSerial


def wire(call) -> bytes:
    """Run a command against a stub device and return the bytes sent on the wire."""
    port = FakeSerial([b"ch> "])
    tx = TinySA(port)
    call(tx)
    return port.written[0]


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (device.get_version, b"version\r"),
        (device.get_id, b"deviceid\r"),
        (lambda tx: device.set_id(tx, 7), b"deviceid 7\r"),
        (device.get_battery, b"vbat\r"),
        (device.get_battery_offset, b"vbat_offset\r"),
        (lambda tx: device.set_battery_offset(tx, 120), b"vbat_offset 120\r"),
        (sweep.get, b"sweep\r"),
        (sweep.get_status, b"status\r"),
        (lambda tx: sweep.set_mode(tx, "normal"), b"sweep normal\r"),
        (lambda tx: sweep.set_start(tx, 410500000), b"sweep start 410500000\r"),
        (lambda tx: sweep.set_stop(tx, 600000000), b"sweep stop 600000000\r"),
        (lambda tx: sweep.set_center(tx, 433000000), b"sweep center 433000000\r"),
        (lambda tx: sweep.set_span(tx, 1000000), b"sweep span 1000000\r"),
        (lambda tx: sweep.set_cw(tx, 433000000), b"sweep cw 433000000\r"),
        (lambda tx: sweep.set_start_stop(tx, 1, 2), b"sweep 1 2\r"),
        (lambda tx: sweep.set_start_stop(tx, 1, 2, 450), b"sweep 1 2 450\r"),
        (lambda tx: sweep.set_time(tx, 250), b"sweeptime 250u\r"),
        (sweep.pause, b"pause\r"),
        (sweep.resume, b"resume\r"),
        (marker.get_all, b"marker\r"),
        (lambda tx: marker.get(tx, 2), b"marker 2\r"),
        (lambda tx: marker.enable(tx, 2), b"marker 2 on\r"),
        (lambda tx: marker.disable(tx, 2), b"marker 2 off\r"),
        (lambda tx: marker.set_freq(tx, 2, 419000000), b"marker 2 419000000\r"),
        (lambda tx: marker.set_trace(tx, 2, 1), b"marker 2 trace 1\r"),
        (lambda tx: marker.move_to_peak(tx, 2), b"marker 2 peak\r"),
        (lambda tx: marker.enable_delta(tx, 2, 1), b"marker 2 delta 1\r"),
        (lambda tx: marker.disable_delta(tx, 2), b"marker 2 delta off\r"),
        (lambda tx: marker.enable_tracking(tx, 2), b"marker 2 tracking on\r"),
        (lambda tx: marker.disable_tracking(tx, 2), b"marker 2 tracking off\r"),
        (trace.get_all, b"trace\r"),
        (lambda tx: trace.get(tx, 1), b"trace 1\r"),
        (trace.get_frequencies, b"frequencies\r"),
        (lambda tx: trace.fetch_value(tx, 1), b"trace 1 value\r"),
        (lambda tx: trace.enable(tx, 1), b"trace 1 view on\r"),
        (lambda tx: trace.disable(tx, 1), b"trace 1 view off\r"),
        (lambda tx: trace.enable_calc(tx, 1, "maxh"), b"calc 1 maxh\r"),
        (lambda tx: trace.disable_calc(tx, 1), b"calc 1 off\r"),
        (lambda tx: trace.set_unit(tx, "dBm"), b"trace dBm\r"),
        (lambda tx: trace.set_ref_level(tx, -30), b"trace reflevel -30\r"),
        (trace.set_ref_level_auto, b"trace reflevel auto\r"),
        (lambda tx: trace.set_scale(tx, 10), b"trace scale 10\r"),
        (signal.enable_spur, b"spur on\r"),
        (signal.disable_spur, b"spur off\r"),
        (signal.enable_auto_spur, b"spur auto\r"),
        (signal.enable_lna, b"lna on\r"),
        (signal.disable_lna, b"lna off\r"),
        (lambda tx: menu.trigger(tx, [6, 2, 1]), b"menu 6 2 1\r"),
        (lambda tx: preset.load(tx, 3), b"load 3\r"),
        (lambda tx: preset.save(tx, 3), b"save 3\r"),
        (lambda tx: raw.execute(tx, "scanraw 1 2 3"), b"scanraw 1 2 3\r"),
    ],
)
def test_wire_command(call, expected):
    assert wire(call) == expected


def test_reset_uses_write_only():
    port = FakeSerial([])
    device.reset(TinySA(port))
    assert port.written == [b"reset\r"]


def test_reset_dfu():
    port = FakeSerial([])
    device.reset(TinySA(port), dfu=True)
    assert port.written == [b"reset dfu\r"]


def test_enable_calc_rejects_invalid_type():
    with pytest.raises(ValueError):
        trace.enable_calc(TinySA(FakeSerial([b"ch> "])), 1, "bogus")


def test_set_unit_rejects_invalid_unit():
    with pytest.raises(ValueError):
        trace.set_unit(TinySA(FakeSerial([b"ch> "])), "dBwrong")


def test_menu_trigger_requires_ids():
    with pytest.raises(ValueError):
        menu.trigger(TinySA(FakeSerial([b"ch> "])), [])


def test_capture_fetches_model_sized_framebuffer():
    width, height = 480, 320
    payload = bytes(width * height * 2)
    port = FakeSerial([b"capture\r\n" + payload + b"ch> "])
    result = capture.fetch_framebuffer(TinySA(port), Model.ULTRA)

    assert len(result) == width * height * 2
    assert port.written == [b"capture\r"]
