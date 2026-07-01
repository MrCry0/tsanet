"""Tests for client-side marker amplitude lookup by nearest frequency bin."""

from __future__ import annotations

from tsanet.controller.marker_lookup import nearest_amplitude


def test_exact_match_returns_that_bin():
    freqs = [100, 200, 300]
    level = [-50.0, -40.0, -30.0]
    assert nearest_amplitude(freqs, level, 200) == -40.0


def test_rounds_to_nearer_neighbor():
    freqs = [100, 200, 300]
    level = [-50.0, -40.0, -30.0]
    assert nearest_amplitude(freqs, level, 240) == -40.0
    assert nearest_amplitude(freqs, level, 260) == -30.0


def test_below_range_clamps_to_first_bin():
    freqs = [100, 200, 300]
    level = [-50.0, -40.0, -30.0]
    assert nearest_amplitude(freqs, level, 0) == -50.0


def test_above_range_clamps_to_last_bin():
    freqs = [100, 200, 300]
    level = [-50.0, -40.0, -30.0]
    assert nearest_amplitude(freqs, level, 1_000_000) == -30.0


def test_empty_input_returns_none():
    assert nearest_amplitude([], [], 100) is None
    assert nearest_amplitude([100], [], 100) is None


def test_uses_shorter_of_mismatched_lengths():
    # A frame caught mid-update where level is one element shorter.
    freqs = [100, 200, 300]
    level = [-50.0, -40.0]
    assert nearest_amplitude(freqs, level, 300) == -40.0
