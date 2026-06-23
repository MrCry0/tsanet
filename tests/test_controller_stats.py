"""Tests for trace statistics computation (brief 6.4, 12)."""

from __future__ import annotations

import math

import pytest

from tsanet.controller.stats import compute_stats


def _approx(a, b, rel=1e-9):
    return math.isclose(a, b, rel_tol=rel)


class TestStats:
    def test_dbm_average_is_linear_power_mean(self):
        # Two dBm values: -10 dBm = 0.1 mW, 0 dBm = 1 mW.
        # Average mW = (0.1 + 1) / 2 = 0.55 mW = 10*log10(0.55) = -2.596... dBm.
        freqs = [100_000_000, 200_000_000]
        values = [-10.0, 0.0]
        result = compute_stats(freqs, values, "dBm", 0, 300_000_000)
        assert _approx(result.average, 10 * math.log10(0.55))

    def test_dbm_median_is_plain_median(self):
        freqs = [100_000_000, 200_000_000, 300_000_000]
        values = [-60.0, -50.0, -70.0]
        result = compute_stats(freqs, values, "dBm", 0, 400_000_000)
        assert result.median == -60.0

    def test_dbmv_average_is_rms_voltage(self):
        # Both 0 dBmV → 1 mV each → RMS = 1 mV → 0 dBmV.
        freqs = [100_000_000, 200_000_000]
        values = [0.0, 0.0]
        result = compute_stats(freqs, values, "dBmV", 0, 300_000_000)
        assert _approx(result.average, 0.0)

    def test_dbmv_median(self):
        freqs = [100_000_000, 200_000_000, 300_000_000]
        values = [10.0, 0.0, 20.0]
        result = compute_stats(freqs, values, "dBmV", 0, 400_000_000)
        assert result.median == 10.0

    def test_voltage_rms_average(self):
        freqs = [100_000_000, 200_000_000]
        values = [3.0, 4.0]
        result = compute_stats(freqs, values, "V", 0, 300_000_000)
        assert _approx(result.average, math.sqrt((9 + 16) / 2))  # RMS = 3.535...

    def test_w_average_is_plain_mean(self):
        freqs = [100_000_000, 200_000_000]
        values = [1.0, 5.0]
        result = compute_stats(freqs, values, "W", 0, 300_000_000)
        assert result.average == 3.0

    def test_raw_average_is_plain_mean(self):
        freqs = [100_000_000, 200_000_000]
        values = [100.0, 200.0]
        result = compute_stats(freqs, values, "RAW", 0, 300_000_000)
        assert result.average == 150.0

    def test_min_max_with_frequencies(self):
        freqs = [100_000_000, 433_920_000, 868_000_000]
        values = [-70.0, -42.0, -80.0]
        result = compute_stats(freqs, values, "dBm", 0, 900_000_000)
        assert result.minimum == -80.0
        assert result.min_freq == 868_000_000
        assert result.maximum == -42.0
        assert result.max_freq == 433_920_000

    def test_range_filtering(self):
        freqs = [100_000_000, 410_500_000, 600_000_000, 900_000_000]
        values = [10.0, 20.0, 30.0, 40.0]
        result = compute_stats(freqs, values, "RAW", 400_000_000, 700_000_000)
        # Only 410.5 and 600 are in range.
        assert _approx(result.average, 25.0)
        assert result.minimum == 20.0
        assert result.maximum == 30.0

    def test_empty_range_raises(self):
        freqs = [100_000_000, 200_000_000]
        values = [1.0, 2.0]
        with pytest.raises(ValueError):
            compute_stats(freqs, values, "dBm", 500_000_000, 600_000_000)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            compute_stats([1, 2], [1.0], "RAW", 0, 10)
