"""``tsanet-gui`` entry point (brief 10, 11.7)."""

from __future__ import annotations

import sys

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    sys.exit(
        "PySide6 is not installed.\n"
        "Install it with:  uv run --extra gui tsanet-gui\n"
        "or:               pip install tsanet[gui]"
    )

from tsanet.controller.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    _ = MainWindow()
    app.exec()


if __name__ == "__main__":
    main()
