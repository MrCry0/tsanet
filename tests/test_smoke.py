import tsanet
from tsanet.controller.cli.app import main as ctl_main
from tsanet.hub.cli import main as hub_main

try:
    from tsanet.controller.gui.app import main as gui_main
except SystemExit:
    gui_main = None


def test_version() -> None:
    assert tsanet.__version__


def test_entry_points_importable() -> None:
    assert callable(hub_main)
    assert callable(ctl_main)
    if gui_main is not None:
        assert callable(gui_main)
