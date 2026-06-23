import tsanet
from tsanet.controller.cli.app import main as ctl_main
from tsanet.controller.gui.app import main as gui_main
from tsanet.hub.cli import main as hub_main


def test_version() -> None:
    assert tsanet.__version__


def test_entry_points_importable() -> None:
    assert callable(hub_main)
    assert callable(ctl_main)
    assert callable(gui_main)
