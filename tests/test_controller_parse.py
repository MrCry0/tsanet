"""Tests for frequency/time argument parsing."""

from __future__ import annotations

import pytest

from tsanet.controller.parse import parse_frequency, parse_time


class TestParseFrequency:
    def test_ghz(self):
        assert parse_frequency("1.5ghz") == 1_500_000_000

    def test_mhz(self):
        assert parse_frequency("100mhz") == 100_000_000

    def test_khz(self):
        assert parse_frequency("250khz") == 250_000

    def test_hz(self):
        assert parse_frequency("5hz") == 5

    def test_short_suffix_g(self):
        assert parse_frequency("2.4g") == 2_400_000_000

    def test_short_suffix_m(self):
        assert parse_frequency("433m") == 433_000_000

    def test_short_suffix_k(self):
        assert parse_frequency("500k") == 500_000

    def test_no_suffix_defaults_to_hz(self):
        assert parse_frequency("1000") == 1000

    def test_decimal(self):
        assert parse_frequency("433.92mhz") == 433_920_000

    def test_integer(self):
        assert parse_frequency("915000000") == 915_000_000

    def test_whitespace(self):
        assert parse_frequency("  100 mhz  ") == 100_000_000

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_frequency("not_a_freq")

    def test_empty(self):
        with pytest.raises(ValueError):
            parse_frequency("")


class TestParseTime:
    def test_seconds(self):
        assert parse_time("1.5s") == 1_500_000

    def test_milliseconds(self):
        assert parse_time("250ms") == 250_000

    def test_microseconds(self):
        assert parse_time("100us") == 100

    def test_no_suffix(self):
        assert parse_time("1000") == 1000

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_time("abc")

    def test_empty(self):
        with pytest.raises(ValueError):
            parse_time("")
