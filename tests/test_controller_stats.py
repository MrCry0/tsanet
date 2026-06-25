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


class TestOccupiedBandwidth:
    def test_flat_power_spans_nearly_full_range(self):
        freqs = list(range(100_000_000, 110_000_000, 1_000_000))
        values = [-50.0] * len(freqs)
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        assert result.occupied_bandwidth_hz == freqs[-1] - freqs[0]

    def test_dominant_spike_collapses_bandwidth(self):
        freqs = list(range(0, 100_000_000, 1_000_000))
        values = [-100.0] * len(freqs)
        values[50] = 0.0  # one spike ~100 dB above the noise floor
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        assert result.occupied_bandwidth_hz == 0

    def test_all_zero_power_raises_instead_of_dividing_by_zero(self):
        # PAPR (peak/average) is undefined for an entirely zero-power trace;
        # this must raise a clear error rather than a ZeroDivisionError.
        freqs = [100_000_000, 200_000_000]
        values = [0.0, 0.0]
        with pytest.raises(ValueError):
            compute_stats(freqs, values, "W", freqs[0], freqs[-1])


class TestPaprAndFlatness:
    def test_flat_dbm_signal_has_zero_papr_and_flatness(self):
        freqs = [100_000_000, 200_000_000, 300_000_000]
        values = [-50.0, -50.0, -50.0]
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        assert result.papr_db == 0.0
        assert result.flatness_db == 0.0

    def test_dbm_flatness_is_max_minus_min(self):
        # For dB-scale units the flatness in dB equals max - min directly.
        freqs = [100_000_000, 200_000_000]
        values = [-80.0, -42.0]
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        assert _approx(result.flatness_db, 38.0)

    def test_papr_matches_hand_computed_ratio(self):
        # power(1mW=0dBm) vs avg(0.01mW dominant + negligible) -> ~20 dB.
        freqs = [100_000_000, 200_000_000, 300_000_000]
        values = [-100.0, 0.0, -100.0]
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        lin = [10 ** (v / 10) for v in values]
        expected = 10 * math.log10(max(lin) / (sum(lin) / len(lin)))
        assert _approx(result.papr_db, expected)

    def test_voltage_flatness_uses_factor_20(self):
        freqs = [100_000_000, 200_000_000]
        values = [1.0, 2.0]
        result = compute_stats(freqs, values, "V", freqs[0], freqs[-1])
        assert _approx(result.flatness_db, 20 * math.log10(2.0))


class TestFieldStrength:
    def test_none_by_default(self):
        freqs = [100_000_000, 200_000_000]
        values = [-50.0, -50.0]
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1])
        assert result.field_strength_dbuvm is None

    def test_dbm_field_strength(self):
        # -50 dBm -> 57 dBuV (the +107 conversion) -> + AF(20) = 77.
        freqs = [100_000_000, 200_000_000]
        values = [-50.0, -50.0]
        result = compute_stats(freqs, values, "dBm", freqs[0], freqs[-1], antenna_factor=20.0)
        assert _approx(result.field_strength_dbuvm, 77.0)

    def test_dbmv_field_strength(self):
        freqs = [100_000_000, 200_000_000]
        values = [10.0, 10.0]
        result = compute_stats(freqs, values, "dBmV", freqs[0], freqs[-1], antenna_factor=5.0)
        assert _approx(result.field_strength_dbuvm, 10.0 + 60.0 + 5.0)

    def test_dbuv_field_strength_is_passthrough_plus_af(self):
        freqs = [100_000_000, 200_000_000]
        values = [30.0, 30.0]
        result = compute_stats(freqs, values, "dBuV", freqs[0], freqs[-1], antenna_factor=3.0)
        assert _approx(result.field_strength_dbuvm, 33.0)

    def test_raw_unit_raises(self):
        freqs = [100_000_000, 200_000_000]
        values = [1.0, 2.0]
        with pytest.raises(ValueError):
            compute_stats(freqs, values, "RAW", freqs[0], freqs[-1], antenna_factor=1.0)
