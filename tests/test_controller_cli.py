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
