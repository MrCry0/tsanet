"""Regression test: the Spectrum tab's colormap dropdown must only ever
offer colormaps pyqtgraph can actually load.

"hot" and "grayscale" were hardcoded into the dropdown but are not local
colormap files in this pyqtgraph release, so picking either crashed with
FileNotFoundError from pyqtgraph.colormap.get(). _available_colormaps()
filters a preferred list against pyqtgraph.colormap.listMaps() instead of
assuming names exist.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from pyqtgraph.colormap import get as get_colormap  # noqa: E402
from pyqtgraph.colormap import listMaps as list_colormaps  # noqa: E402

from tsanet.controller.gui.spectrum_panel import (  # noqa: E402
    _PREFERRED_COLORMAPS,
    _available_colormaps,
)


def test_every_available_colormap_actually_loads():
    for name in _available_colormaps():
        get_colormap(name)  # must not raise


def test_hot_and_grayscale_are_not_offered():
    # These were the two names that crashed get_colormap() with
    # FileNotFoundError; they must never reappear in the offered list.
    offered = _available_colormaps()
    assert "hot" not in offered
    assert "grayscale" not in offered


def test_only_actually_available_maps_are_offered():
    available = set(list_colormaps())
    for name in _available_colormaps():
        assert name in available


def test_falls_back_to_listed_maps_if_none_preferred_are_available(monkeypatch):
    import tsanet.controller.gui.spectrum_panel as m

    monkeypatch.setattr(m, "_PREFERRED_COLORMAPS", ["definitely-not-a-real-map"])
    result = m._available_colormaps()
    assert result  # falls back to whatever pyqtgraph actually has
    assert "definitely-not-a-real-map" not in result


def test_preferred_colormaps_constant_has_no_known_bad_names():
    assert "hot" not in _PREFERRED_COLORMAPS
    assert "grayscale" not in _PREFERRED_COLORMAPS
