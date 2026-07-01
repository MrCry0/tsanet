"""Tests for client-side trace hold computation (live/min/max/maxd/avg/quasi)."""

from __future__ import annotations

import pytest

from tsanet.controller.trace_hold import (
    MAXD_DECAY_STEP,
    QUASI_CHARGE_ALPHA,
    QUASI_DISCHARGE_ALPHA,
    TraceHold,
)


class TestLiveMode:
    def test_passes_through_each_frame_unchanged(self):
        hold = TraceHold("live")
        assert hold.update([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]
        assert hold.update([4.0, 5.0, 6.0]) == [4.0, 5.0, 6.0]


class TestMinHold:
    def test_tracks_minimum_across_frames(self):
        hold = TraceHold("min")
        assert hold.update([5.0, -10.0, 3.0]) == [5.0, -10.0, 3.0]
        assert hold.update([1.0, -20.0, 4.0]) == [1.0, -20.0, 3.0]
        assert hold.update([9.0, 9.0, 9.0]) == [1.0, -20.0, 3.0]

    def test_reset_clears_accumulated_minimum(self):
        hold = TraceHold("min")
        hold.update([1.0, 1.0])
        hold.update([-5.0, -5.0])
        hold.reset()
        assert hold.update([10.0, 10.0]) == [10.0, 10.0]


class TestMaxHold:
    def test_tracks_maximum_across_frames(self):
        hold = TraceHold("max")
        assert hold.update([5.0, -10.0, 3.0]) == [5.0, -10.0, 3.0]
        assert hold.update([1.0, -2.0, 30.0]) == [5.0, -2.0, 30.0]

    def test_reset_clears_accumulated_maximum(self):
        hold = TraceHold("max")
        hold.update([10.0])
        hold.reset()
        assert hold.update([1.0]) == [1.0]


class TestMaxDecay:
    def test_holds_at_peak_when_new_value_is_higher(self):
        hold = TraceHold("maxd")
        assert hold.update([5.0]) == [5.0]
        assert hold.update([9.0]) == [9.0]

    def test_decays_toward_new_value_by_fixed_step_when_lower(self):
        hold = TraceHold("maxd")
        hold.update([10.0])
        assert hold.update([0.0]) == [10.0 - MAXD_DECAY_STEP]

    def test_decay_never_drops_below_the_new_sample(self):
        hold = TraceHold("maxd")
        hold.update([10.0])
        # Even after many frames, decay stops once it reaches the live value.
        for _ in range(1000):
            result = hold.update([9.99])
        assert result == [9.99]

    def test_reset_clears_accumulated_peak(self):
        hold = TraceHold("maxd")
        hold.update([100.0])
        hold.reset()
        assert hold.update([1.0]) == [1.0]


class TestQuasiPeak:
    def test_charges_toward_a_rising_value(self):
        hold = TraceHold("quasi")
        assert hold.update([0.0]) == [0.0]
        result = hold.update([10.0])
        assert result == pytest.approx([QUASI_CHARGE_ALPHA * 10.0])

    def test_discharges_slowly_toward_a_falling_value(self):
        hold = TraceHold("quasi")
        hold.update([10.0])
        result = hold.update([0.0])
        assert result == pytest.approx([10.0 + QUASI_DISCHARGE_ALPHA * (0.0 - 10.0)])

    def test_reset_clears_accumulated_state(self):
        hold = TraceHold("quasi")
        hold.update([10.0])
        hold.reset()
        assert hold.update([1.0]) == [1.0]


class TestAverage:
    def test_averages_over_window_of_frames(self):
        hold = TraceHold("avg", window=3)
        assert hold.update([0.0, 0.0]) == [0.0, 0.0]
        assert hold.update([2.0, 4.0]) == [1.0, 2.0]
        assert hold.update([4.0, 8.0]) == pytest.approx([2.0, 4.0])
        # Window is full at 3 frames; the oldest frame drops out next.
        assert hold.update([4.0, 8.0]) == pytest.approx([10 / 3, 20 / 3])

    def test_reset_clears_accumulated_frames(self):
        hold = TraceHold("avg", window=4)
        hold.update([100.0])
        hold.reset()
        assert hold.update([1.0]) == [1.0]


class TestInputValidation:
    def test_rejects_unknown_mode(self):
        with pytest.raises(ValueError):
            TraceHold("bogus")

    def test_rejects_non_positive_window(self):
        with pytest.raises(ValueError):
            TraceHold("avg", window=0)


class TestFrameLengthChange:
    def test_min_hold_resets_on_length_change_instead_of_crashing(self):
        hold = TraceHold("min")
        hold.update([1.0, 2.0, 3.0])
        # A shorter/longer frame (e.g. sweep points changed) must not
        # raise from zip()'s length mismatch — it should just restart.
        assert hold.update([9.0, 9.0]) == [9.0, 9.0]

    def test_avg_resets_on_length_change_instead_of_crashing(self):
        hold = TraceHold("avg", window=5)
        hold.update([1.0, 2.0, 3.0])
        assert hold.update([9.0, 9.0]) == [9.0, 9.0]

    def test_maxd_resets_on_length_change_instead_of_crashing(self):
        hold = TraceHold("maxd")
        hold.update([1.0, 2.0, 3.0])
        assert hold.update([9.0, 9.0]) == [9.0, 9.0]

    def test_quasi_resets_on_length_change_instead_of_crashing(self):
        hold = TraceHold("quasi")
        hold.update([1.0, 2.0, 3.0])
        assert hold.update([9.0, 9.0]) == [9.0, 9.0]
