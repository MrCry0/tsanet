"""Tests for version parsing and model identification."""

from __future__ import annotations

import pytest

from tsanet.common.errors import ProtocolError
from tsanet.device.model import Model, parse_version


def test_parse_ultra_version():
    info = parse_version("tinySA4_v1.4-143-g864bb27 HW Version:V0.4.5.1")

    assert info.model is Model.ULTRA
    assert info.model_string == "tinySA4"
    assert info.firmware == "1.4-143-g864bb27"
    assert info.hardware == "0.4.5.1"


def test_parse_version_in_multiline_text():
    text = "garbage boot line\r\ntinySA4_v1.4 HW Version:V0.4.5.1\r\n"
    info = parse_version(text)

    assert info.model is Model.ULTRA
    assert info.hardware == "0.4.5.1"


def test_parse_version_rejects_unknown():
    with pytest.raises(ProtocolError):
        parse_version("not a version string")
