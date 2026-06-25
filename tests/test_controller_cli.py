"""Regression tests for tsanet-ctl error handling and device targeting.

These exercise the CLI module's functions directly (no real socket), since
the bugs they guard against were all "the CLI claims success/crashes with a
traceback instead of reporting a clean error" -- argument parsing and
response handling, not RPC behavior, which is already covered elsewhere.
"""

from __future__ import annotations

import pytest
import typer

from tsanet.controller.cli import app as cli_app


@pytest.fixture(autouse=True)
def _reset_client():
    cli_app._client = None
    yield
    cli_app._client = None


def test_freq_passes_through_valid_frequency():
    assert cli_app._freq("100mhz") == 100_000_000


def test_freq_raises_clean_error_on_invalid_frequency():
    """A typo'd frequency (e.g. '600mh') must not crash with a traceback."""
    with pytest.raises(typer.Exit) as exc_info:
        cli_app._freq("600mh")
    assert "invalid frequency" in str(exc_info.value.exit_code)


def _fake_sweep_call(get_response: str):
    def fake_call(domain, op, **kwargs):
        assert domain == "sweep"
        if op == "get":
            return get_response
        return None  # the setters' own return value is unused

    return fake_call


def test_sweep_range_reports_device_clamped_points(monkeypatch, capsys):
    """The device can silently clamp points (e.g. 900 -> 450 max); the CLI
    must report what was actually applied, not echo the request back."""
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("2400000000 2490000000 450"))
    cli_app.sweep_range(start="2400mhz", stop="2490mhz", points=900)
    out = capsys.readouterr().out
    assert "450" in out
    assert "900" not in out


def test_sweep_range_warns_when_points_clamped(monkeypatch, capsys):
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("2400000000 2490000000 450"))
    cli_app.sweep_range(start="2400mhz", stop="2490mhz", points=900)
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert "900" in err and "450" in err


def test_sweep_range_no_warning_when_points_match(monkeypatch, capsys):
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("2400000000 2490000000 450"))
    cli_app.sweep_range(start="2400mhz", stop="2490mhz", points=450)
    assert capsys.readouterr().err == ""


def test_sweep_start_reports_actual_queried_value(monkeypatch, capsys):
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("433000000 868000000"))
    cli_app.sweep_start(hz="100mhz")
    out = capsys.readouterr().out
    assert "433" in out


def test_sweep_start_warns_when_clamped_to_device_minimum(monkeypatch, capsys):
    # Requested 1 Hz but the device floors to its actual minimum start.
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("100000 868000000"))
    cli_app.sweep_start(hz="1hz")
    err = capsys.readouterr().err
    assert "warning" in err.lower()
    assert "start" in err.lower()


def test_sweep_state_raises_cleanly_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(cli_app, "_call", _fake_sweep_call("not a sweep response"))
    with pytest.raises(typer.Exit) as exc_info:
        cli_app._sweep_state()
    assert "unexpected sweep response" in str(exc_info.value.exit_code)


def test_trace_stats_reports_empty_range_cleanly(monkeypatch):
    """compute_stats() raising on an empty range must surface as a clean error."""
    monkeypatch.setattr(
        cli_app,
        "_call",
        lambda domain, op, **kwargs: {
            "frequencies": [100, 200, 300],
            "traces": {"2": [1.0, 2.0, 3.0]},
        },
    )
    with pytest.raises(typer.Exit) as exc_info:
        cli_app.trace_stats(trace_id=2, start="10ghz", stop="11ghz", unit="dBm")
    assert "no data points in range" in str(exc_info.value.exit_code)


def test_trace_save_reports_invalid_trace_id_cleanly():
    """A non-numeric --trace ID (e.g. '1,abc') must not crash with a traceback."""
    with pytest.raises(typer.Exit) as exc_info:
        cli_app.trace_save(trace_ids="1,abc", output=None)
    assert "invalid trace ID" in str(exc_info.value.exit_code)


def _patch_trace_data(monkeypatch, freqs, values, trace_id=2):
    monkeypatch.setattr(
        cli_app,
        "_call",
        lambda domain, op, **kwargs: {"frequencies": freqs, "traces": {str(trace_id): values}},
    )


def test_trace_stats_omits_field_strength_without_antenna_factor(monkeypatch, capsys):
    _patch_trace_data(monkeypatch, [100, 200, 300], [-50.0, -50.0, -50.0])
    cli_app.trace_stats(trace_id=2, start="0hz", stop="1000hz", unit="dBm")
    out = capsys.readouterr().out
    assert "Field strength" not in out
    assert "Channel power" in out
    assert "Occupied BW" in out
    assert "PAPR" in out
    assert "Flatness" in out


def test_trace_stats_channel_power_is_the_headline_indicator(monkeypatch, capsys):
    """Channel power must always be shown, ahead of every other indicator."""
    _patch_trace_data(monkeypatch, [100, 200, 300], [-50.0, -50.0, -50.0])
    cli_app.trace_stats(trace_id=2, start="0hz", stop="1000hz", unit="dBm", antenna_factor=20.0)
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    labels = [line.split(":")[0].strip() for line in lines[1:]]
    assert labels[0] == "Channel power"
    assert labels[1] == "Field strength"


def test_trace_stats_shows_field_strength_with_antenna_factor(monkeypatch, capsys):
    _patch_trace_data(monkeypatch, [100, 200, 300], [-50.0, -50.0, -50.0])
    cli_app.trace_stats(trace_id=2, start="0hz", stop="1000hz", unit="dBm", antenna_factor=20.0)
    out = capsys.readouterr().out
    # -50 dBm -> 57 dBuV (+107) -> + 20 dB/m antenna factor = 77.0 dBuV/m.
    assert "Field strength : 77.0 dBuV/m" in out


class _FakeRpcClient:
    """Stand-in for RpcClient that records calls instead of touching a socket."""

    instances: list["_FakeRpcClient"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.connected = False
        self.calls: list[tuple[str, str, dict]] = []
        _FakeRpcClient.instances.append(self)

    def connect(self) -> None:
        self.connected = True

    def call(self, domain: str, op: str, **kwargs: object) -> object:
        self.calls.append((domain, op, kwargs))
        return None


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeRpcClient.instances.clear()
    yield
    _FakeRpcClient.instances.clear()


def test_device_option_selects_device_after_connect(monkeypatch):
    """--device must select that device, in-process, right after connecting.

    Regression for the dropped 'devices select' subcommand: each tsanet-ctl
    invocation is its own connection, so selection has to happen within the
    same _setup() call as the rest of the command, not as a separate step.
    """
    monkeypatch.setattr(cli_app, "RpcClient", _FakeRpcClient)
    cli_app._setup(
        config_path=None,
        mode="dial",
        transport="tcp",
        address="127.0.0.1",
        port=7777,
        device="dev-2",
    )
    client = _FakeRpcClient.instances[-1]
    assert client.connected
    assert client.calls == [("devices", "select", {"device_id": "dev-2"})]


def test_no_device_option_skips_select(monkeypatch):
    monkeypatch.setattr(cli_app, "RpcClient", _FakeRpcClient)
    cli_app._setup(
        config_path=None,
        mode="dial",
        transport="tcp",
        address="127.0.0.1",
        port=7777,
        device=None,
    )
    client = _FakeRpcClient.instances[-1]
    assert client.calls == []


class _RefusingRpcClient(_FakeRpcClient):
    """Simulates dial() hitting an unreachable hub (ECONNREFUSED)."""

    def connect(self) -> None:
        raise ConnectionRefusedError(111, "Connection refused")


def test_setup_reports_unreachable_hub_cleanly(monkeypatch, capsys):
    """An unreachable hub must report a clean message, not a raw traceback."""
    monkeypatch.setattr(cli_app, "RpcClient", _RefusingRpcClient)
    with pytest.raises(typer.Exit) as exc_info:
        cli_app._setup(
            config_path=None,
            mode="dial",
            transport="tcp",
            address="127.0.0.1",
            port=17999,
            device=None,
        )
    assert exc_info.value.exit_code == 1
    assert "could not reach 127.0.0.1:17999" in capsys.readouterr().err
