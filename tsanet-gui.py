#!/usr/bin/env python3
"""Run tsanet-gui directly from the source tree.

Usage:
    python tsanet-gui.py
    ./tsanet-gui.py

The script auto-detects the project's ``.venv`` so it works without
activating the virtualenv first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

_venv_py = str(_ROOT / ".venv" / "bin" / "python")
if sys.executable != _venv_py and os.path.exists(_venv_py):
    os.execv(_venv_py, [_venv_py, *sys.argv])

_src = str(_ROOT / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from tsanet.controller.gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
