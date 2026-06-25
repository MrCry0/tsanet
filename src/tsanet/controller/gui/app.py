"""``tsanet-gui`` entry point."""

from __future__ import annotations

import argparse
import logging
import sys

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    sys.exit(
        "PySide6 is not installed.\n"
        "Install it with:  uv run --extra gui tsanet-gui\n"
        "or:               pip install tsanet[gui]"
    )

from tsanet.common.logging import configure as configure_logging
from tsanet.controller.gui.main_window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="tsanet graphical controller")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show informational messages")
    parser.add_argument(
        "--debug", action="store_true", help="Show detailed debug output (implies --verbose)"
    )
    args, remaining = parser.parse_known_args()

    level = logging.WARNING
    if args.verbose:
        level = logging.INFO
    if args.debug:
        level = logging.DEBUG
    configure_logging(level, stream=sys.stderr)

    app = QApplication(sys.argv[:1] + remaining)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
