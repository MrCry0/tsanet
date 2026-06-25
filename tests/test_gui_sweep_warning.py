"""Tests for the GUI's sweep value mismatch warning.

MainWindow._sweep_mismatch_warning is a pure @staticmethod, so it can be
exercised directly without instantiating a QMainWindow or QApplication.
"""

from __future__ import annotations

from tsanet.controller.gui.main_window import MainWindow


def test_no_warning_when_nothing_requested():
    assert MainWindow._sweep_mismatch_warning(None, 100, 200, 450) is None


def test_no_warning_when_points_match():
    assert (
        MainWindow._sweep_mismatch_warning({"points": 450}, 2_400_000_000, 2_490_000_000, 450)
        is None
    )


def test_warns_when_points_clamped():
    # Real-world case: the device caps points at 450, silently, no error.
    warning = MainWindow._sweep_mismatch_warning({"points": 900}, 2_400_000_000, 2_490_000_000, 450)
    assert warning is not None
    assert "900" in warning
    assert "450" in warning


def test_warns_when_start_frequency_clamped():
    warning = MainWindow._sweep_mismatch_warning({"start": 1}, 100_000, 868_000_000, None)
    assert warning is not None
    assert "start" in warning


def test_warns_when_center_derived_value_differs():
    warning = MainWindow._sweep_mismatch_warning(
        {"center": 433_000_000}, 400_000_000, 500_000_000, None
    )
    assert warning is not None
    assert "center" in warning


def test_no_warning_when_points_not_reported_by_device():
    # The device's "sweep get" response omitted points; can't compare, so
    # this must not be treated as a mismatch.
    assert MainWindow._sweep_mismatch_warning({"points": 900}, 100, 200, None) is None


def test_multiple_mismatches_are_all_reported():
    warning = MainWindow._sweep_mismatch_warning(
        {"start": 1, "stop": 900_000_000, "points": 900},
        100_000,
        868_000_000,
        450,
    )
    assert warning is not None
    assert "start" in warning
    assert "stop" in warning
    assert "points" in warning
